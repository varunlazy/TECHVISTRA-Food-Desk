import sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import server
from http.server import ThreadingHTTPServer
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as tmp:
 server.DB=Path(tmp)/'test.sqlite3';server.init_db()
 h=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=h.serve_forever,daemon=True).start()
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True);page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto('http://127.0.0.1:'+str(h.server_port))
  page.get_by_role('heading',name='Set up your food desk').wait_for()
  assert page.locator('#login-username').is_disabled()
  page.locator('#login-password').fill('administrator123');page.locator('#confirm-password').fill('differentpass123')
  page.locator('#login-submit').click();page.get_by_text('Passwords do not match.',exact=True).wait_for()
  page.locator('#confirm-password').fill('administrator123');page.locator('#login-submit').click()
  page.get_by_role('heading',name='Welcome back').wait_for()
  assert page.locator('#login-username').is_enabled()
  assert page.locator('#confirm-password').is_disabled()
  page.locator('#login-password').fill('administrator123');page.locator('#login-submit').click()
  page.get_by_role('heading',name='Food distribution overview').wait_for()
  assert not errors,errors
  print('PASS: fresh setup submits, mismatched passwords show feedback, setup switches to login, admin login opens dashboard; no JavaScript errors.')
  browser.close()
 h.shutdown();h.server_close()
