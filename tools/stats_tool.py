"""
Advertising stats tool for MCP.
Returns mock statistics about ad campaigns: ads run, CPC, and other relevant metrics.
"""
from typing import Dict, Any, List, Optional

# Fake ad campaign data
FAKE_ADS: List[Dict[str, Any]] = [
    {
        "ad_id": "ad_001",
        "campaign": "Spring 2025 Brand Awareness",
        "ad_name": "Hero Banner - Product Launch",
        "channel": "Google Display",
        "impressions": 2_450_000,
        "clicks": 18_340,
        "spend_usd": 12_450.00,
        "cpc_usd": 0.68,
        "cpm_usd": 5.08,
        "ctr_pct": 0.75,
        "conversions": 892,
        "conversion_rate_pct": 4.86,
        "cpa_usd": 13.96,
        "date_range": "2025-02-01 to 2025-02-28",
    },
    {
        "ad_id": "ad_002",
        "campaign": "Spring 2025 Brand Awareness",
        "ad_name": "Video Pre-roll 15s",
        "channel": "YouTube",
        "impressions": 1_120_000,
        "clicks": 8_960,
        "spend_usd": 8_400.00,
        "cpc_usd": 0.94,
        "cpm_usd": 7.50,
        "ctr_pct": 0.80,
        "conversions": 403,
        "conversion_rate_pct": 4.49,
        "cpa_usd": 20.84,
        "date_range": "2025-02-01 to 2025-02-28",
    },
    {
        "ad_id": "ad_003",
        "campaign": "Q1 Retargeting",
        "ad_name": "Cart Abandonment - 10% Off",
        "channel": "Meta (Facebook/Instagram)",
        "impressions": 890_000,
        "clicks": 26_700,
        "spend_usd": 5_340.00,
        "cpc_usd": 0.20,
        "cpm_usd": 6.00,
        "ctr_pct": 3.00,
        "conversions": 1_602,
        "conversion_rate_pct": 6.00,
        "cpa_usd": 3.33,
        "date_range": "2025-01-15 to 2025-02-15",
    },
    {
        "ad_id": "ad_004",
        "campaign": "Q1 Retargeting",
        "ad_name": "Browse Abandonment - Dynamic",
        "channel": "Meta (Facebook/Instagram)",
        "impressions": 1_550_000,
        "clicks": 31_000,
        "spend_usd": 6_200.00,
        "cpc_usd": 0.20,
        "cpm_usd": 4.00,
        "ctr_pct": 2.00,
        "conversions": 1_860,
        "conversion_rate_pct": 6.00,
        "cpa_usd": 3.33,
        "date_range": "2025-01-15 to 2025-02-15",
    },
    {
        "ad_id": "ad_005",
        "campaign": "Search - High Intent",
        "ad_name": "Branded Search - Exact Match",
        "channel": "Google Search",
        "impressions": 320_000,
        "clicks": 19_200,
        "spend_usd": 14_400.00,
        "cpc_usd": 0.75,
        "cpm_usd": 45.00,
        "ctr_pct": 6.00,
        "conversions": 1_728,
        "conversion_rate_pct": 9.00,
        "cpa_usd": 8.33,
        "date_range": "2025-02-01 to 2025-02-28",
    },
    {
        "ad_id": "ad_006",
        "campaign": "Search - High Intent",
        "ad_name": "Non-Brand Search - Product Terms",
        "channel": "Google Search",
        "impressions": 680_000,
        "clicks": 20_400,
        "spend_usd": 24_480.00,
        "cpc_usd": 1.20,
        "cpm_usd": 36.00,
        "ctr_pct": 3.00,
        "conversions": 1_224,
        "conversion_rate_pct": 6.00,
        "cpa_usd": 20.00,
        "date_range": "2025-02-01 to 2025-02-28",
    },
]


def execute(
    campaign: Optional[str] = None,
    channel: Optional[str] = None,
    min_spend_usd: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Return fake advertising stats: ads run, CPC, CPM, CTR, spend, conversions, etc.
    Filter by campaign name, channel, or minimum spend if provided.
    """
    results = list(FAKE_ADS)

    if campaign and campaign.strip():
        q = campaign.strip().lower()
        results = [a for a in results if q in a.get("campaign", "").lower()]
    if channel and channel.strip():
        q = channel.strip().lower()
        results = [a for a in results if q in a.get("channel", "").lower()]
    if min_spend_usd is not None:
        results = [a for a in results if a.get("spend_usd", 0) >= min_spend_usd]

    total_spend = sum(a.get("spend_usd", 0) for a in results)
    total_impressions = sum(a.get("impressions", 0) for a in results)
    total_clicks = sum(a.get("clicks", 0) for a in results)
    total_conversions = sum(a.get("conversions", 0) for a in results)

    return {
        "ads": results,
        "summary": {
            "ad_count": len(results),
            "total_spend_usd": round(total_spend, 2),
            "total_impressions": total_impressions,
            "total_clicks": total_clicks,
            "total_conversions": total_conversions,
            "overall_ctr_pct": round(100 * total_clicks / total_impressions, 2) if total_impressions else 0,
            "overall_cpc_usd": round(total_spend / total_clicks, 2) if total_clicks else 0,
        },
        "filters_applied": {
            "campaign": campaign or None,
            "channel": channel or None,
            "min_spend_usd": min_spend_usd,
        },
    }


TOOL_METADATA = {
    "name": "ad_stats",
    "description": (
        "Get advertising system statistics: which ads were run, CPC (cost per click), CPM, CTR, spend, "
        "impressions, clicks, conversions, and CPA. Data is mock/fake for demo purposes. "
        "Optional filters: campaign (substring match), channel (substring match), min_spend_usd."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "campaign": {
                "type": "string",
                "description": "Filter by campaign name (substring match).",
            },
            "channel": {
                "type": "string",
                "description": "Filter by channel (e.g. 'Google', 'Meta', 'YouTube').",
            },
            "min_spend_usd": {
                "type": "number",
                "description": "Only include ads with spend >= this amount (USD).",
            },
        },
        "required": [],
    },
}
