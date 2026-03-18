# 🌴 Central America Property Finder

Investment property finder for **Costa Rica**, **Panama**, and **Belize** — ranked by weighted scoring for Canadian investors.

## 🏠 Live Site

👉 **[View Site](https://central-america-property-scraper.vercel.app/)**

## Features

- 30 properties from Properstar, Point2Homes & Encuentra24
- Weighted scoring system with 6 adjustable sliders (Price, Airport, Beach, Size, Yield, Move-in Ready)
- Interactive property cards with Google Maps links
- Airbnb rental income comparison ranked by gross yield
- Filter by country, area, max price, airport distance
- Detail modals with full stats, badges, and listing links
- Prices in both USD and CAD
| [**ROI Calculator**](roi-calculator.html) | 📊 Interactive yield, cap rate & cash-on-cash calculator          |

## 🛠️ Tech Stack

- **Zero dependencies** — vanilla HTML5, CSS3, ES6 JavaScript
- **Google Fonts** — Inter (300–900)
- **Auto-nav** — `nav.js` discovers pages via GitHub API
- **Python scraper** — `requests` + `BeautifulSoup4` for property listings

## 🔧 Scraper

```bash
pip install requests beautifulsoup4
python scrape_ca_properties.py
```

Outputs `ca_properties.json` with listings from Encuentra24 (CR/PA) and Point2Homes (BZ).

## 🌎 Related

- [EU Rental Properties](https://github.com/matisaar/eu-rental-properties) — European vacation rental research

## 📋 License

MIT
