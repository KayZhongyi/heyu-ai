from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from app.trend_discovery import (
    DouyinOpenPlatformSource,
    FeedSource,
    ManualTrend,
    TrendCandidate,
    TrendDiscoveryRequest,
    TrendDiscoveryService,
    rank_candidate,
)

NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)


def _request(**overrides):
    data = {
        "product_name": "当季番茄",
        "selling_points": ["清晨采摘", "自然成熟", "当天发货"],
        "audience": "喜欢新鲜食材的城市家庭",
        "platform": "douyin",
        "limit": 8,
    }
    data.update(overrides)
    return TrendDiscoveryRequest.model_validate(data)


def test_rss_and_atom_success_preserve_source_and_times():
    rss = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel>
      <item>
        <title>盛夏番茄采摘挑战</title>
        <link>https://news.example/trends/tomato</link>
        <pubDate>Wed, 15 Jul 2026 09:30:00 GMT</pubDate>
        <description>清晨田间采摘，展示当天发货过程</description>
      </item>
    </channel></rss>""".encode()
    atom = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>一周新鲜食材清单</title>
        <link href="/posts/fresh-food"/>
        <updated>2026-07-14T07:00:00+08:00</updated>
        <summary>给城市家庭的买菜攻略</summary>
      </entry>
    </feed>""".encode()

    def handler(request: httpx.Request) -> httpx.Response:
        content = rss if request.url.path.endswith("rss.xml") else atom
        return httpx.Response(200, content=content, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = TrendDiscoveryService(feed_client=client).discover(
            _request(
                feed_sources=[
                    FeedSource(url="https://feeds.example/rss.xml", label="产地资讯 RSS"),
                    FeedSource(url="https://feeds.example/atom.xml", label="生活方式 Atom"),
                ]
            ),
            now=NOW,
        )

    assert result.used_fallback is False
    by_title = {item.candidate.title: item.candidate for item in result.items}
    rss_item = by_title["盛夏番茄采摘挑战"]
    assert rss_item.source_type == "rss"
    assert rss_item.source_label == "产地资讯 RSS"
    assert rss_item.source_url == "https://news.example/trends/tomato"
    assert rss_item.captured_at == NOW
    assert rss_item.published_at == datetime(2026, 7, 15, 9, 30, tzinfo=UTC)
    atom_item = by_title["一周新鲜食材清单"]
    assert atom_item.source_type == "atom"
    assert atom_item.source_label == "生活方式 Atom"
    assert atom_item.source_url == "https://feeds.example/posts/fresh-food"
    assert atom_item.published_at == datetime(2026, 7, 13, 23, 0, tzinfo=UTC)


def test_network_failure_returns_explicit_seasonal_and_evergreen_fallbacks():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("feed timed out", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = TrendDiscoveryService(feed_client=client, timeout_seconds=0.5).discover(
            _request(
                feed_sources=[
                    FeedSource(url="https://feeds.example/unavailable", label="测试热点源")
                ]
            ),
            now=NOW,
        )

    assert result.used_fallback is True
    assert {item.candidate.source_type for item in result.items} == {"seasonal", "evergreen"}
    assert any("暂时不可用" in warning for warning in result.warnings)
    assert any("实时来源当前没有可用结果" in warning for warning in result.warnings)
    assert "不是实时热度" in result.metric_note
    for item in result.items:
        assert item.candidate.source_url is None
        assert item.candidate.published_at is None


def test_relevance_ranking_prefers_product_fit_and_filmability():
    relevant = TrendCandidate(
        title="当季番茄清晨采摘挑战：从田间到当天发货",
        source_url="https://example.test/relevant",
        source_label="测试来源",
        captured_at=NOW,
        published_at=NOW - timedelta(hours=4),
        source_type="rss",
        summary="用短视频给城市家庭展示自然成熟番茄的采摘、对比和发货过程",
    )
    unrelated = TrendCandidate(
        title="办公桌收纳颜色趋势",
        source_url="https://example.test/unrelated",
        source_label="测试来源",
        captured_at=NOW,
        published_at=NOW - timedelta(hours=1),
        source_type="rss",
        summary="面向职场人群的桌面布置建议",
    )
    request = _request()

    ranked_relevant = rank_candidate(relevant, request=request, now=NOW)
    ranked_unrelated = rank_candidate(unrelated, request=request, now=NOW)

    assert ranked_relevant.fit_score > ranked_unrelated.fit_score
    assert ranked_relevant.recommendation == "recommended"
    assert ranked_unrelated.recommendation == "skip"
    assert ranked_relevant.fit.product.score == 100
    assert ranked_relevant.fit.selling_points.score == 100
    assert ranked_relevant.fit.filmability.score > ranked_unrelated.fit.filmability.score
    assert ranked_relevant.fit.product.explanation
    assert ranked_relevant.recommendation_reason


def test_manual_source_is_deduplicated_and_limit_is_enforced():
    duplicated = ManualTrend(
        title="番茄采摘挑战",
        source_url="https://example.test/topic",
        source_label="组员手工选题",
        published_at=NOW,
        summary="清晨采摘",
    )
    result = TrendDiscoveryService().discover(
        _request(
            manual_trends=[
                duplicated,
                duplicated.model_copy(),
                ManualTrend(title="番茄开箱", source_label="组员手工选题"),
                ManualTrend(title="番茄做法", source_label="组员手工选题"),
            ],
            limit=2,
        ),
        now=NOW,
    )

    assert len(result.items) == 2
    assert len({item.candidate.title for item in result.items}) == 2
    manual = next(item.candidate for item in result.items if item.candidate.title == "番茄采摘挑战")
    assert manual.source_type == "manual"
    assert manual.source_label == "组员手工选题"
    assert manual.source_url == "https://example.test/topic"
    assert manual.published_at == NOW


def test_duplicate_title_keeps_newer_traceable_feed_candidate():
    rss = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel>
      <item>
        <title>番茄采摘挑战</title>
        <link>https://news.example/trends/tomato-harvest</link>
        <pubDate>Thu, 16 Jul 2026 06:30:00 GMT</pubDate>
        <description>清晨采摘、自然成熟和当天发货的现场短视频</description>
      </item>
    </channel></rss>""".encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=rss, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = TrendDiscoveryService(feed_client=client).discover(
            _request(
                manual_trends=[
                    ManualTrend(
                        title="番茄采摘挑战",
                        source_label="手工备选",
                        published_at=NOW - timedelta(days=7),
                    )
                ],
                feed_sources=[
                    FeedSource(url="https://feeds.example/rss.xml", label="农业资讯 RSS")
                ],
            ),
            now=NOW,
        )

    duplicates = [item.candidate for item in result.items if item.candidate.title == "番茄采摘挑战"]
    assert len(duplicates) == 1
    assert duplicates[0].source_type == "rss"
    assert duplicates[0].source_label == "农业资讯 RSS"
    assert duplicates[0].source_url == "https://news.example/trends/tomato-harvest"
    assert duplicates[0].published_at == datetime(2026, 7, 16, 6, 30, tzinfo=UTC)


def test_duplicate_url_keeps_newer_candidate_even_when_title_changes():
    shared_url = "https://news.example/trends/tomato"
    result = TrendDiscoveryService().discover(
        _request(
            manual_trends=[
                ManualTrend(
                    title="番茄采摘现场",
                    source_url=shared_url,
                    source_label="较早来源",
                    published_at=NOW - timedelta(days=5),
                ),
                ManualTrend(
                    title="清晨番茄采摘挑战",
                    source_url=shared_url,
                    source_label="更新来源",
                    published_at=NOW - timedelta(hours=2),
                    summary="自然成熟番茄的采摘、对比和发货过程",
                ),
            ]
        ),
        now=NOW,
    )

    matches = [item.candidate for item in result.items if item.candidate.source_url == shared_url]
    assert len(matches) == 1
    assert matches[0].title == "清晨番茄采摘挑战"
    assert matches[0].source_label == "更新来源"


def test_timeliness_score_drops_after_ninety_days_and_unknown_is_explicit():
    request = _request()
    recent = TrendCandidate(
        title="当季番茄采摘挑战",
        source_label="测试来源",
        captured_at=NOW,
        published_at=NOW - timedelta(days=1),
        source_type="rss",
    )
    old = recent.model_copy(update={"published_at": NOW - timedelta(days=120)})
    unknown = recent.model_copy(update={"published_at": None})

    ranked_recent = rank_candidate(recent, request=request, now=NOW)
    ranked_old = rank_candidate(old, request=request, now=NOW)
    ranked_unknown = rank_candidate(unknown, request=request, now=NOW)

    assert ranked_recent.fit.timeliness.score > ranked_old.fit.timeliness.score
    assert ranked_old.fit.timeliness.score == 30
    assert ranked_unknown.fit.timeliness.score == 48
    assert "未提供发布时间" in ranked_unknown.fit.timeliness.explanation


def test_unconnected_douyin_adapter_never_calls_network_or_fabricates_platform_data():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"data": {"list": [{"title": "不应出现"}]}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = TrendDiscoveryService(douyin_client=client).discover(
            _request(douyin=DouyinOpenPlatformSource()),
            now=NOW,
        )

    assert calls == 0
    assert result.used_fallback is True
    assert all(item.candidate.source_type != "douyin-open-platform" for item in result.items)
    assert any("未连接" in warning and "未请求或伪造" in warning for warning in result.warnings)


def test_result_has_fit_scores_but_no_fake_heat_or_performance_numbers():
    result = TrendDiscoveryService().discover(_request(), now=NOW)
    serialized = result.model_dump(mode="json")
    text = str(serialized).lower()

    assert "fit_score" in text
    assert "实时热度、播放量、互动量或销量预测" in result.metric_note
    for forbidden_field in (
        "heat_score",
        "hotness",
        "popularity",
        "view_count",
        "engagement_count",
        "sales_prediction",
    ):
        assert forbidden_field not in text
