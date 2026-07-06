import requests, re
session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
})
r = session.get('https://news.google.com/rss/articles/CBMiJWh0dHBzOi8vd3d3LmJsb29tYmVyZ3RlY2hub3ouY29tL3Jvb20v0gEA?hl=id&gl=ID&ceid=ID%3Aid')
print(r.text[:500])
match = re.search(r'URL=(.*?)"', r.text, re.IGNORECASE)
if match:
    print('FOUND:', match.group(1))
else:
    print('Not found')
