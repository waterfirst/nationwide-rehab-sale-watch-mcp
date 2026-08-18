import pytest

from nationwide_rehab_sale_watch_mcp.server import _parse_list, _validate_court_url


def test_parse_current_court_table_shape() -> None:
    html = """
    <table class="tableHor"><tbody><tr>
      <td>196</td><td>서울회생법원</td><td>파산관재인</td>
      <td><a href="/rel/realboard/RealboardView.work?seq_id=34895">자산 매각 공고</a></td><td>490</td>
    </tr></tbody></table>
    """

    rows = _parse_list("slb", html)

    assert rows[0]["seq_id"] == "34895"
    assert rows[0]["title"] == "자산 매각 공고"


def test_detail_fetch_blocks_non_court_urls() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        _validate_court_url("https://example.com/private")
