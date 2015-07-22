## NOMEN


Python script to turn first and last names of people into relevant email addresses


####Required Fields:

First name

Last Name

####Optional Fields:


Personal Domains


Keywords: non url-based keywords

####Process

The program is designed to combine web crawling with brute-force email generation

With web crawling, a depth of 1-2 is recommended for the given domain URLs
With brute-force email generation, the first and last names are used in a string template
to generate email addresses from given URLs

The email is then filtered and send to the MX checker and clearbit for final confirmation


Filtering out candidates, in the case where multiple emails are valid, this script will score the
results by fullname comparison (levenshtein distance) between the input name and the reverse email
search provided by Clearbit.

The result should be a dictionary with email as the key and its edit distance as the value. Lower is
better


####TO RUN

echo [firstname] [lastname] {url1}...{urln} {keywords...} | python run.py

the script reads from the stdin

Make sure to export your linkedin
    username as LINKEDIN_USERNAME,
    password as LINKEDIN_PASSWORD, and
    clearbit private key as CLEARBIT_KEY
as environmental variables.
