#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import inspect
import io
import base64
import json
import requests
import time
import datetime
import contextlib

from typing import List, Set, Dict, Tuple, Optional

import selenium
import selenium.webdriver



# vvvvvvvvvvvv WAITOR vvvvvvvvvvvv

# Source:
#   https://stackoverflow.com/a/25651197
#   http://www.obeythetestinggoat.com/how-to-get-selenium-to-wait-for-page-load-after-a-click.html



def wait_for(condition_function):
    start_time = time.time()
    while time.time() < start_time + 3:
        if condition_function():
            return True
        else:
            time.sleep(0.1)
    raise Exception('Timeout waiting for {}'.format(condition_function.__name__))
    
    
@contextlib.contextmanager
def wait_for_page_load(browser):
    old_page = browser.find_element(selenium.webdriver.common.by.By.TAG_NAME, "html")

    yield

    def page_has_loaded():
        new_page = browser.find_element(selenium.webdriver.common.by.By.TAG_NAME, "html")
        return new_page.id != old_page.id

    wait_for(page_has_loaded)

    
    
# ^^^^^^^^^^^^ WAITOR ^^^^^^^^^^^^ 



def getScriptDir(followSymlinks = True):
  # Inspired from:
  #   http://stackoverflow.com/a/6209894
  #   http://stackoverflow.com/a/22881871
  if getattr(sys, 'frozen', False): # py2exe, PyInstaller, cx_Freeze
    path = os.path.abspath(sys.executable)
  else:
    path = inspect.getframeinfo(inspect.currentframe()).filename
    path = os.path.abspath(path)        
  if followSymlinks:
    path = os.path.realpath(path)
  return os.path.dirname(path)
  
  
  
def readBinaryFile(filename):
  with open(filename, "rb") as f:
    data = f.read()
  return data
  
def writeBinaryFile(filename, content):
  with open(filename, "wb") as f:
    f.write(content)

    
  

# https://docs.python-requests.org/en/latest/user/quickstart/

# https://tarunlalwani.com/post/reusing-existing-browser-session-selenium/

# https://firefox-source-docs.mozilla.org/testing/geckodriver/Usage.html

# WebDriver wire protocol:
#   https://github.com/SeleniumHQ/selenium/wiki/JsonWireProtocol

  
    
class Session:
  def __init__(self, start_time, session_creation_response):
    self.start_time                = start_time
    self.session_creation_response = session_creation_response

  def get_session_id(self) -> str:
    return json.loads(self.session_creation_response)["value"]["sessionId"]
    
  @classmethod
  def from_dict(cls, session_dict: Dict):
    return cls(    
      start_time                = session_dict["start_time"],  
      session_creation_response = base64.b64decode(session_dict["session_creation_response"]).decode("utf-8")
      )
    
  def to_dict(self):
    return {
      "start_time":                self.start_time,
      "session_creation_response": base64.b64encode(self.session_creation_response.encode("utf-8")).decode("ascii")
    }

    
class Connection:
  def __init__(self, name: str, host: str, port: int, driver: str = "default"):
    if (port < 1) or (port > 65535):
      raise RuntimeError(f"Invalid port number specified!")

    self.name   = name
    self.host   = host
    self.port   = port
    self.driver = driver
    
    
class ConnectionSessionPair:
  def __init__(self, connection: Connection, func_store_session, func_retrieve_session):
  
    if not isinstance(connection.host, str):
      raise RuntimeError(f"Connection '{connection.name}: Invalid type for host specification!")
    if not isinstance(connection.port, int):
      raise RuntimeError(f"Connection '{connection.name}: Invalid type for port specification!")
    if (connection.port < 1) or (connection.port > 65535):
      raise RuntimeError(f"Connection '{connection.name}: Invalid port number specified!")
    if (connection.driver != "default") and (connection.driver != "firefox"):
      raise RuntimeError(f"Connection '{connection.name}: Invalid driver specified!")
      
    self._host   = connection.host
    self._port   = connection.port
    self._driver = connection.driver
    
    self.func_store_session   = func_store_session
    self.func_retrieve_session = func_retrieve_session
    
    
  def get_host(self):
    return self._host
    
  def get_port(self):
    return self._port
    
  def get_driver(self):
    return self._driver
    
  def get_session(self) -> Session:
    # Create or re-use session
  
    if not self.is_wd_service_running():
      raise RuntimeError("Could not reach target host! Is the WebDriver service running?")

    if self.is_any_session_active():
      print("Attempting to use cached session...")

      # Retrieve saved session information      
      session_dict = self.func_retrieve_session()
      if session_dict is None:
        raise RuntimeError("There is an active session on the WebDriver, but we have no idea which one, as there is no stored information about it!")
      session = Session.from_dict(session_dict)
      
      if not self.is_session_valid(session):
        raise RuntimeError("There is an active session on the WebDriver, but it's not the one we stored!")
     
      print(f"Using cached session '{session.get_session_id()}', created: {session.start_time}")
     
    else:
      print("Attempting to create a new session...")
      session = self.create_session()
      self.func_store_session(session.to_dict())

      print(f"Using new session '{session.get_session_id()}'")
      
    return session
    
    
  def is_wd_service_running(self) -> bool:
    try:
      r = requests.get(f"http://{self._host}:{self._port}/status")
      return r.status_code == 200
    except requests.exceptions.ConnectionError as _:
      return False
    
    
  def is_any_session_active(self) -> bool:
    r = requests.get(f"http://{self._host}:{self._port}/status")

    if r.status_code != 200:
      raise RuntimeError("Could not determine WebDriver service status")

    r_data = json.loads(r.text)
    return r_data["value"]["ready"] == False
      
    
  def create_session(self) -> Session:
    headers = {"Content-Type": "application/json"}
    data    = '{"capabilities": {"alwaysMatch": {"acceptInsecureCerts": true}}}'

    r = requests.post(f"http://{self._host}:{self._port}/session", headers = headers, data = data)

    if r.status_code != 200:
      raise RuntimeError("Could not create new session")

    r_data = json.loads(r.text)

    return Session(
      start_time                = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
      session_creation_response = r.text
    )
  
    
  def is_session_valid(self, session: Session) -> bool:
    r = requests.get(f"http://{self._host}:{self._port}/session/{session.get_session_id()}/url")

    if r.status_code == 200:
      return True
    elif r.status_code == 404:
      return False
    else:
      raise RuntimeError("Unexpected response status code!")


      
class WebDriverSessionCache:

  def __init__(self, connections: List[Connection], cache_file: str):
  
    self.cache_file = cache_file

    self.connection_session_pairs = {}
    for connection in connections:
      if connection.name in self.connection_session_pairs:
        raise RuntimeError(f"Connection '{connection.name}' defined more than once!")
        
      func_store_session    = lambda session_dict : self.store_session(connection.name, session_dict)
      func_retrieve_session = lambda              : self.retrieve_session(connection.name)
        
      self.connection_session_pairs[connection.name] = ConnectionSessionPair(
        connection = connection,
        func_store_session    = func_store_session,
        func_retrieve_session = func_retrieve_session)
      

  @staticmethod
  def normalize_connection_name(connection_name: str) -> str:
    # TODO: IMPLEMENT REAL STUF HERE!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    return connection_name
      
      
  def store_session(self, connection_name, session_dict):
    connection_name = WebDriverSessionCache.normalize_connection_name(connection_name)
    data = {connection_name: session_dict}
    writeBinaryFile(self.cache_file, json.dumps(data, indent = 2).encode("utf-8"))
      
      
  def retrieve_session(self, connection_name) -> Dict:

    if not os.path.exists(self.cache_file):
      return None

    with open(self.cache_file) as f:
      data_json = json.load(f)
  
    connection_name = WebDriverSessionCache.normalize_connection_name(connection_name)

    if not connection_name in data_json:
      return None
    
    return data_json[connection_name]
      


  def get_remote_connection(self, connection_name, *args, **kwargs):
    if not connection_name in self.connection_session_pairs:
      raise RuntimeError(f"Invalid connection name '{connection_name}'!")

    connection_session_pair = self.connection_session_pairs[connection_name]
            
    host = connection_session_pair.get_host()
    port = connection_session_pair.get_port()
    
    session_creation_response = connection_session_pair.get_session().session_creation_response
    
    # The base class can be specified, because some features might only be
    # available for specific drivers, e.g., the ability to take full-page
    # screenshots
    if connection_session_pair.get_driver() == "default":
      BaseClass = selenium.webdriver.remote.remote_connection.RemoteConnection
    elif connection_session_pair.get_driver() == "firefox":
      BaseClass = selenium.webdriver.firefox.remote_connection.FirefoxRemoteConnection
    else:
      raise RuntimeError("Unknown driver type!")

      
    class ExistingRemoteConnection(BaseClass):
      # Extends selenium.webdriver.remote.remote_connection.RemoteConnection,
      # or a more specialized version of it, so that it re-uses an existing
      # remote connection instead of creating a new one

      def __init__(self, session_creation_response, *args, **kwargs):
        self.session_creation_response = session_creation_response
        super(ExistingRemoteConnection, self).__init__(*args, **kwargs)

      def execute(self, command, params):
        if command == selenium.webdriver.remote.webdriver.Command.NEW_SESSION:
          return json.loads(self.session_creation_response)
        else:
          return super(ExistingRemoteConnection, self).execute(command, params)

    
    return ExistingRemoteConnection(
      session_creation_response = session_creation_response,
      remote_server_addr        = f"http://{host}:{port}",
      *args, **kwargs)
    
  
class GeckoDriverSessionCache(WebDriverSessionCache):
  def __init__(self, *args, **kwargs):
    super(GeckoDriverSessionCache, self).__init__(*args, **kwargs)

  
  
def ffox_full_page_screenshot_as_png(driver):
  # Take full page screenshot (currently only supported by Firefox)
  return base64.b64decode(driver.execute("FULL_PAGE_SCREENSHOT")["value"])  
    
    
def get_public_ip(driver) -> str:
  with wait_for_page_load(driver):
    driver.get('https://api.ipify.org/?format=text')
  body = driver.find_element(selenium.webdriver.common.by.By.TAG_NAME, "body")
  return body.text
  
    
def main():

  print(f"Selenium version: {selenium.__version__}")
  
  
  connections = [
    Connection(name = "testifox", host = "127.0.0.1", port = 14444, driver = "firefox")
  ]
      
  wd_session_cache = WebDriverSessionCache(
    connections = connections,
    cache_file  = os.path.join(getScriptDir(), "session_cache.json")
    )
  
  
  
  driver = selenium.webdriver.remote.webdriver.WebDriver(
    command_executor = wd_session_cache.get_remote_connection("testifox"),
    options          = selenium.webdriver.FirefoxOptions()
  )

  print(f"Public IP: {get_public_ip(driver)}")

    
    
  with wait_for_page_load(driver):
    driver.get("https://www.startpage.com/")

  
  search_field = driver.find_element(selenium.webdriver.common.by.By.ID, "q")
  search_field.send_keys("Lebkuchen")
  
  search_button = driver.find_element(selenium.webdriver.common.by.By.CLASS_NAME, "search-form-home__button-desktop")
  
  with wait_for_page_load(driver):
    search_button.click()
  
  time.sleep(3.0)
  
  
  print("Screenshot time!")
  
  print(driver.current_url)
  
  # Take screenshot
  screenshot          = ffox_full_page_screenshot_as_png(driver)
  screenshot_filename = os.path.join(getScriptDir(), "screenshot.png")
  writeBinaryFile(screenshot_filename, screenshot)
  

  driver.find_element(selenium.webdriver.common.by.By.LINK_TEXT, 'Impressum').click()

  
  ##  driver.find_element_by_id('kw').send_keys('千锋教育')
  ##  sleep(2)
  ##  driver.find_element_by_id('su').click()
  ##  sleep(2)

  ##  print(driver.title)
  ##  
  ##  print(driver.page_source)

    
  
  
if __name__ == "__main__":
  main()
