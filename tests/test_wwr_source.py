from pathlib import Path

from job_scout.sources.wwr import parse_wwr_rss


def test_parse_wwr_rss_fixture():
    payload = Path("tests/fixtures/wwr_sample.xml").read_text(encoding="utf-8")
    postings = parse_wwr_rss(payload, since_days=4000)

    assert len(postings) == 2
    first = postings[0]
    assert first.source == "wwr"
    assert first.title == "Data Governance Specialist"
    assert first.company == "DataCo"
    assert first.location_text == "Europe"
    assert first.remote_type == "full-remote"
    assert first.salary_text == "€75k-€90k"
    assert first.url.startswith("https://weworkremotely.com/")


def test_parse_wwr_rss_html_headquarters_and_company():
    payload = """<rss version="2.0">
  <channel>
    <title>We Work Remotely</title>
    <item>
      <title>Gitlab: Principal Product Manager, Security &amp; Compliance</title>
      <link>https://weworkremotely.com/remote-jobs/gitlab-principal-product-manager-security-compliance</link>
      <guid>gitlab-principal-product-manager-security-compliance</guid>
      <pubDate>Wed, 09 Apr 2026 09:30:00 GMT</pubDate>
      <description><![CDATA[
        <p><strong>Headquarters:</strong> Remote, United Kingdom </p>
        <div><p>Security and compliance portfolio leadership.</p></div>
      ]]></description>
    </item>
    <item>
      <title>Equip Health: Product Manager II - Reporting &amp; Analytics</title>
      <link>https://weworkremotely.com/remote-jobs/equip-health-product-manager-ii-reporting-analytics</link>
      <guid>equip-health-product-manager-ii-reporting-analytics</guid>
      <pubDate>Wed, 09 Apr 2026 11:30:00 GMT</pubDate>
      <description><![CDATA[
        <p><strong>Headquarters:</strong> Remote - USA</p>
        <p>Analytics product role.</p>
      ]]></description>
    </item>
  </channel>
</rss>"""

    postings = parse_wwr_rss(payload, since_days=4000)

    assert len(postings) == 2
    assert postings[0].company == "Gitlab"
    assert postings[0].title == "Principal Product Manager, Security & Compliance"
    assert postings[0].location_text == "United Kingdom"
    assert postings[0].location_country == "United Kingdom"
    assert "Headquarters:" in postings[0].description_snippet

    assert postings[1].company == "Equip Health"
    assert postings[1].title == "Product Manager II - Reporting & Analytics"
    assert postings[1].location_text == "USA"
    assert postings[1].location_country == "USA"
