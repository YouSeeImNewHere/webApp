#!/usr/bin/env python
import os
import sys
from datetime import date

try:
  from urllib.request import Request, build_opener, HTTPCookieProcessor
  from urllib.error import HTTPError, URLError
  from urllib.parse import urlencode
  import cookielib
except ImportError:
  from urllib2 import Request, build_opener, HTTPCookieProcessor, HTTPError, URLError
  from urllib import urlencode
  import cookielib


def req(opener, method, url, data=None):
  payload = None
  headers = {}
  if data is not None:
    payload = urlencode(data).encode("utf-8")
    headers["Content-Type"] = "application/x-www-form-urlencoded"
  request = Request(url, data=payload, headers=headers)
  request.get_method = lambda: method
  try:
    resp = opener.open(request, timeout=20)
    return resp.getcode(), ""
  except HTTPError as e:
    return e.code, str(e)
  except URLError as e:
    return 0, str(e)


def check(code, allowed, label):
  ok = code in allowed
  print("[{}] {} -> {}".format("OK" if ok else "FAIL", label, code))
  return ok


def main():
  base = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
  secret = os.environ.get("SMOKE_SECRET", "").strip()
  cookie_jar = cookielib.CookieJar()
  opener = build_opener(HTTPCookieProcessor(cookie_jar))
  all_ok = True

  code, _ = req(opener, "GET", "{}/login".format(base))
  all_ok &= check(code, (200,), "GET /login")
  code, _ = req(opener, "GET", "{}/static/pages/home/home.html".format(base))
  all_ok &= check(code, (200,), "GET home html")
  code, _ = req(opener, "GET", "{}/static/pages/analytics/analytics.html".format(base))
  all_ok &= check(code, (200,), "GET analytics html")

  if secret:
    code, _ = req(opener, "POST", "{}/login".format(base), {"secret": secret})
    all_ok &= check(code, (200, 302, 303), "POST /login")
  else:
    print("[INFO] SMOKE_SECRET not set; protected endpoint checks may return 401.")

  month = date.today().strftime("%Y-%m")
  checks = [
    ("/page/home?tx_limit=15", "GET /page/home"),
    ("/reports/monthly?month={}".format(month), "GET /reports/monthly"),
    ("/page/budget", "GET /page/budget"),
  ]
  for path, label in checks:
    code, err = req(opener, "GET", "{}{}".format(base, path))
    if code == 0:
      print("[FAIL] {} -> {}".format(label, err))
      all_ok = False
      continue
    all_ok &= check(code, (200, 401), label)

  return 0 if all_ok else 1


if __name__ == "__main__":
  sys.exit(main())
