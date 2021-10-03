
# Simple WebDriver test without Selenium

# Requires the WebDriver client module from wpt (web-platform-tests):
#   https://github.com/web-platform-tests/wpt/tree/master/tools/webdriver


import webdriver

session = webdriver.Session("127.0.0.1", 14444)

session.url = "https://mozilla.org"
print("The current URL is %s" % session.url)

#  with webdriver.Session("127.0.0.1", 14444) as session:
#    session.url = "https://mozilla.org"
#    print("The current URL is %s" % session.url)

