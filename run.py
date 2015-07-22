from bs4 import BeautifulSoup, SoupStrainer
import requests
import dns.resolver
import smtplib
import logging
import re
import json
import os
from linkedin_parser import LinkedInParser
from copy import deepcopy
import fileinput
import time
import clearbit
from multiprocessing import Pool

logger = logging.getLogger('Nomen')
logger.setLevel(logging.DEBUG)
console = logging.StreamHandler()
console.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console.setFormatter(formatter)
logger.addHandler(console)

GOOGLE_URL_PREFIX = "https://www.google.com/search?q={}"
LINKEDIN_URL_ROOT = "https://www.linkedin.com/pub/dir/{}/{}"
CLEARBIT_API_ROOT = "https://person.clearbit.com/v1/people/email/{}"
EMAIL_ADDR = ["info@gmail.com", "contact@gmail.com", "contact@yahoo.com", "info@yahoo.com",
                      "support@google.com"]

regex = re.compile(("([a-z0-9!#$%&'*+\/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+\/=?^_`"
                "{|}~-]+)*(@|\sat\s)(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(\.|"
                "\sdot\s))+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)"))

LINKEDIN_USERNAME = os.environ.get('LINKEDIN_USERNAME')
LINKEDIN_PASSWORD = os.environ.get('LINKEDIN_PASSWORD')
clearbit.key = os.environ.get('CLEARBIT_KEY')

linkedin_parser = LinkedInParser(LINKEDIN_USERNAME,LINKEDIN_PASSWORD)

def regex_email(content):
    return [email[0] for email in re.findall(regex, content) if not email[0].startswith('//')]

def scape_page(url,get_func,emails,current_depth,max_depth):
    if current_depth<=max_depth:
        r = get_func(url)

        content = r if isinstance(r,str) else r.content
        emails.extend(regex_email(content))
        for link in BeautifulSoup(content, 'html.parser',parse_only=SoupStrainer('a')):
            if link.has_attr('href') and link['href'].startswith('http'):
                scape_page(link['href'],get_func,emails,current_depth+1,max_depth)

def scrape_linkedin(name):
    emails = []
    logger.debug("scraping linkedin")
    first, last = name.split(' ')
    url = LINKEDIN_URL_ROOT.format(first, last)
    # r = s.get(url)

    content = linkedin_parser.loadPage(url)
    # print content
    for li in BeautifulSoup(content,'html.parser').findAll('strong'):
        sLink = li.find('a')
        if sLink:
            scape_page(sLink['href'],linkedin_parser.loadPage,emails,1,1)

    return emails

def scrape_google(name,keywords=None):
    emails = []

    google_query = name.replace(' ',"+")

    if keywords and keywords != '':
        new_keywords = keywords.replace(' ','+')
        google_query += '+'+new_keywords

    google_query_url = GOOGLE_URL_PREFIX.format(google_query)
    r = requests.get(google_query_url)
    emails.extend(regex_email(r.content))

    soup = BeautifulSoup(r.content,'html.parser')
    for li in soup.findAll('li', attrs={'class':'g'}):
        sLink = li.find('a')
        if 'http' in sLink['href']:
            #skip the ads
            continue
        child_url = "https://www.google.com"+sLink['href']
        emails.extend(regex_email(r.content))
        scape_page(child_url,requests.get,emails,1,1)

    return emails

def get_brute_force_email(name,urls):
    logger.debug("generating brute force email address")
    emails = set()
    email_urls = set(deepcopy(urls))
    email_urls.add('gmail.com')
    firstname,lastname = name.split(' ')
    a = "{}.{}"
    b = "{}{}"

    usernames = []
    usernames.append(a.format(firstname,lastname))
    usernames.append(b.format(firstname[0],lastname))
    usernames.append(b.format(firstname,lastname[0]))
    usernames.append(b.format(lastname[0],firstname))
    usernames.append(b.format(firstname,lastname))
    usernames.append(firstname)

    for url in email_urls:
        domain = url.replace('http://','').replace('https://','').replace('www','')
        if '/' in domain:
            continue

        for username in usernames:
            username = username.strip()
            emails.add(username+'@'+domain)

    return emails

def scrape_email(name, urls=[], keywords=None):
    emails = []
    emails.extend(scrape_linkedin(name))
    emails.extend(scrape_google(name, keywords))
    emails.extend(get_brute_force_email(name,urls))

    for url in urls:
        logger.debug("scraping: {}".format(url))
        get_func = requests.get if 'linkedin' in url else linkedin_parser.loadPage
        scape_page(url,get_func,emails,1,1)
    return emails

def _filter_emails(emails):
    ret = set()
    for email in emails:
        if '.png' in email or '.jpg' in email or '.jpeg' in email:
            continue
        if ' ' in email:
            continue
        ret.add(email.lower())
    return ret

# Step one, generate all possible email leads
def query_name_for_email_leads(name, urls=[], keywords=None):
    logger.debug("scraping the web for potential email addresses")
    emails = scrape_email(name, urls, keywords)
    emails = _filter_emails(emails)
    logger.debug(emails)
    return emails

# Step two, check for email validity
# RDNS checks for lookup domain name
def _get_mx_hosts(host):
    ret = dns.resolver.query(host,'MX')
    return [r.exchange.to_text() for r in ret]

def mx_check(email):
    hosts = _get_mx_hosts(email.split('@')[1])
    for host in hosts:
        time.sleep(1)
        host = host[:-1] if host[-1]=='.' else host

        # try each host
        try:
            smtp = smtplib.SMTP()
            smtp.connect(host)
        except Exception as e:
            logger.error('{} continuing'.format(e))
            continue

        # say HELO
        try:
            smtp.ehlo_or_helo_if_needed()
        except Exception as e:
            logger.error('{} continuing'.format(e))
            continue

        # first try to validate without identifying a from email
        v_code, v_msg = smtp.verify(email)
        logger.debug("{} {}".format(v_code,v_msg))

        # should probably throttle due to black/greylisting :/
        if v_code and v_code!=250:
            for from_addr in EMAIL_ADDR:
                from_code, from_msg = smtp.mail(from_addr)
                logger.debug("{} {}".format(from_code,from_msg))

                if (from_code and from_code==250):
                    # accepted, now ask for our email

                    rcpt_code, rcpt_msg = smtp.mail(email)
                    if rcpt_code and rcpt_code == 250:
                        return True

                    if rcpt_code and rcpt_code == 550:
                        return False
                else:
                    continue
    return False

def levenshtein(s1, s2):
    #https://en.wikibooks.org/wiki/Algorithm_Implementation/Strings/Levenshtein_distance#Python
    if len(s1) < len(s2):
        return levenshtein(s2, s1)

    # len(s1) >= len(s2)
    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1 # j+1 instead of j since previous_row and current_row are one character longer
            deletions = current_row[j] + 1       # than s2
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]

def validate_emails(name,emails):
    logger.debug("validating email addresses")
    mx_passed = []
    for email in emails:
        if mx_check(email):
            mx_passed.append(email)
            logger.debug('{} is good'.format(email))

    ret_dict = {}
    for email in mx_passed:
        time.sleep(2)

        person = clearbit.Person.find(email=email, stream=True)
        if person != None:
            fullName = person['name']['fullName'].strip().lower()
            score = levenshtein(fullName,name)
            ret_dict[email] = score
        else:
            continue

    return ret_dict

def process_func(payload):
    name,urls,keywords = payload
    emails = query_name_for_email_leads(name,urls,keywords)
    email_dict = validate_emails(name,emails)
    return email_dict

if __name__ == '__main__':
    p = Pool(5)
    input_params = []
    for input_param in fileinput.input():
        param_list = input_param.split(' ')
        name = ' '.join(param_list[:2])
        urls = set([param for param in param_list if 'http' in param])
        keywords = ' '.join(set(param_list)-urls)
        input_params.append((name,urls,keywords))
    ret = p.map(process_func,input_params)
    print "resulting dict", ret
