## NOMEN


Python script to turn first and last names of people into relevant email addresses


####Required Fields:

First name

Last Name

####Optional Fields:

Middle name


Personal Domain


linkedin_url


####Process

The program is designed to combine web crawling with brute-force email generation

With web crawling, a depth of 1-2 is recommended for the given domain URLs
With brute-force email generation, the first and last names are used in a string template
to generate email addresses from given URLs

The email is then filtered and send to the MX checker and clearbit for final confirmation

####TO RUN

./run [firstname] [lastname] {url1}...{urln} {keywords...}
