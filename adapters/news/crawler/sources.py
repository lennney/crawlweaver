"""Source registry — known news sites to crawl.

Each source has a URL (homepage or article list) and a site_type hint.
Add new sites here. The LLM figures out extraction selectors automatically.

Anti-bot requirements per source:
  - "none": plain requests works
  - "stealth": needs Scrapling/Playwright (Cloudflare Turnstile etc.)
  - "proxy": needs geo-specific proxy (CloudFront WAF, IP block)
"""

SOURCES = [
    {
        "name": "Oddity Central",
        "url": "https://www.odditycentral.com",
        "site_type": "wordpress_news",
        "anti_bot": "none",
    },
    {
        "name": "Philstar",
        "url": "https://www.philstar.com/",
        "site_type": "news_portal",
        "anti_bot": "stealth",  # Cloudflare Turnstile, ~20s overhead
    },
    # Geo-blocked (needs UK proxy):
    # {"name": "Mirror", "url": "https://www.mirror.co.uk/", "anti_bot": "proxy"},
]
