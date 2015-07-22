from bs4 import BeautifulSoup, SoupStrainer
import requests
import dns.resolver
import smtplib
import logging
import re
import os
from linkedin_parser import LinkedInParser
from copy import deepcopy
import fileinput

logger = logging.getLogger('Nomen')
logger.setLevel(logging.DEBUG)

console = logging.StreamHandler()
console.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console.setFormatter(formatter)

logger.addHandler(console)

GOOGLE_URL_PREFIX = "https://www.google.com/search?q={}"
LINKEDIN_URL_ROOT = "https://www.linkedin.com/pub/dir/{}/{}"

EMAIL_ADDR = ["info@gmail.com", "contact@gmail.com", "contact@yahoo.com", "info@yahoo.com",
                      "support@google.com"]

regex = re.compile(("([a-z0-9!#$%&'*+\/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+\/=?^_`"
                "{|}~-]+)*(@|\sat\s)(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(\.|"
                "\sdot\s))+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)"))

LINKEDIN_USERNAME = os.environ.get('LINKEDIN_USERNAME')
LINKEDIN_PASSWORD = os.environ.get('LINKEDIN_PASSWORD')
CLEARBIT_KEY = os.environ.get('CLEARBIT_KEY')

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

def scrape_google(name,keywords="ORNL"):
    emails = []

    google_query = name.replace(' ',"+")

    if keywords:
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
    # emails.extend(scrape_linkedin(name))
    # emails.extend(scrape_google(name, keywords))
    emails.extend(get_brute_force_email(name,urls))

    for url in urls:
        logger.debug("scraping: {}".format(url))
        get_func = requests.get if 'linkedin' in url else linkedin_parser.loadPage
        scape_page(url,get_func,emails,1,1)
    return emails

def _filter_emails(emails):
    ret = set()
    for email in emails:
        if '.png' in email:
            continue
        if ' ' in email:
            continue
        ret.add(email.lower())
    return ret

# Step one, generate all possible email leads
def query_name(name, urls=[], keywords=None):
    logger.debug("scraping the web for potential email addresses")
    emails = scrape_email(name, urls, keywords)
    emails = _filter_emails(emails)
    logger.debug(emails)
    logger.debug("validating email addresses")
    for email in emails:
        if verify_email(email):
            logger.debug('{} is good'.format(email)) 

# Step two, check for email validity
# RDNS checks for lookup domain name
def _get_mx_hosts(host):
    ret = dns.resolver.query(host,'MX')
    return [r.exchange.to_text() for r in ret]

def verify_email(email):
    hosts = _get_mx_hosts(email.split('@')[1])
    for host in hosts:
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

if __name__ == '__main__':
    for input_param in fileinput.input():
        param_list = input_param.split(' ')
        name = ' '.join(param_list[:2])
        urls = set([param for param in param_list if 'http' in param])
        keywords = ' '.join(set(param_list)-urls)
        query_name(name,urls,keywords)
