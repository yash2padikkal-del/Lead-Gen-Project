import requests
from xml.etree import ElementTree

URL = "https://www.nike.com/sitemap-v2-pdp-en-in.xml"

headers = {
    "User-Agent": "Mozilla/5.0"
}

try:

    response = requests.get(
        URL,
        headers=headers,
        timeout=(5, 15)
    )

    print("Status:", response.status_code)
    print("Content-Type:", response.headers.get("Content-Type"))
    print("Response length:", len(response.content))

    print("\nFIRST 5000 CHARACTERS:")
    print(response.text[:5000])

    root = ElementTree.fromstring(response.content)

    print("\nROOT:", root.tag)

    print("\nFIRST 20 XML ENTRIES:")

    for entry in list(root)[:20]:

        for element in entry:

            print(element.tag, ":", element.text)

        print("--------------------")

except Exception as e:

    print("ERROR:", e)