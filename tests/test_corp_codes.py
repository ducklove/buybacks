from io import BytesIO
from zipfile import ZipFile

from scripts.buybacks.fetch_corp_codes import parse_corp_code_zip


def make_corp_code_zip(xml: str) -> bytes:
    payload = BytesIO()
    with ZipFile(payload, "w") as archive:
        archive.writestr("CORPCODE.xml", xml)
    return payload.getvalue()


def test_parse_corp_code_zip_keeps_six_character_listed_stock_codes():
    payload = make_corp_code_zip(
        """
        <result>
          <list>
            <corp_code>00126380</corp_code>
            <corp_name>Samsung Electronics</corp_name>
            <stock_code>005930</stock_code>
            <modify_date>20260620</modify_date>
          </list>
          <list>
            <corp_code>99999999</corp_code>
            <corp_name>Mirae Asset Securities 2 Preferred B</corp_name>
            <stock_code>00680K</stock_code>
            <modify_date>20260620</modify_date>
          </list>
          <list>
            <corp_code>88888888</corp_code>
            <corp_name>Invalid Short Code</corp_name>
            <stock_code>12345</stock_code>
            <modify_date>20260620</modify_date>
          </list>
        </result>
        """
    )

    companies = parse_corp_code_zip(payload)

    assert [company.stock_code for company in companies] == ["005930", "00680K"]
