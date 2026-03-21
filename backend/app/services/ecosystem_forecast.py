"""Ecosystem Weather Forecast — predict 7-day content weather based on health trends."""

import json
import logging
from datetime import date, timedelta
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

# Weather states and their meanings
WEATHER_STATES = {
    "sunny": {"icon": "sun", "label": "Sunny", "description": "Improving metrics expected"},
    "cloudy": {"icon": "cloud", "label": "Cloudy", "description": "Stable, no major changes"},
    "rainy": {"icon": "cloud-rain", "label": "Rainy", "description": "Slight decline expected"},
    "stormy": {"icon": "cloud-lightning", "label": "Stormy", "description": "Significant issues ahead"},
}


class EcosystemForecastService:
    """Generate 7-day content ecosystem weather forecasts."""

    async def generate_forecast(self, db: asyncpg.Connection, site_id: UUID) -> list[dict]:
        """Generate a 7-day forecast based on current trends and health data."""

        today = date.today()

        # Get recent health score trend (last 14 days)
        health_history = await db.fetch(
            """SELECT score, recorded_at::date as day
               FROM health_score_history
               WHERE site_id = $1 AND recorded_at >= $2
               ORDER BY recorded_at DESC""",
            site_id, today - timedelta(days=14),
        )

        # Get cluster health distribution
        clusters = await db.fetch(
            """SELECT ecosystem_state, health_score, post_count
               FROM clusters WHERE site_id = $1""",
            site_id,
        )

        # Get decaying posts count
        decaying_count = await db.fetchval(
            """SELECT COUNT(*) FROM post_health ph
               JOIN posts p ON p.id = ph.post_id
               WHERE p.site_id = $1 AND ph.trend = 'declining'""",
            site_id,
        ) or 0

        total_posts = await db.fetchval(
            "SELECT COUNT(*) FROM posts WHERE site_id = $1", site_id,
        ) or 1

        # Calculate trend direction
        trend_direction = self._calculate_trend(health_history)
        decay_ratio = decaying_count / max(total_posts, 1)
        swamp_count = sum(1 for c in clusters if c["ecosystem_state"] == "swamp")
        desert_count = sum(1 for c in clusters if c["ecosystem_state"] == "desert")
        problem_ratio = (swamp_count + desert_count) / max(len(clusters), 1)

        # Generate 7-day forecast
        forecast = []
        for day_offset in range(7):
            forecast_date = today + timedelta(days=day_offset)
            weather = self._predict_day(
                day_offset=day_offset,
                trend_direction=trend_direction,
                decay_ratio=decay_ratio,
                problem_ratio=problem_ratio,
                is_weekend=forecast_date.weekday() >= 5,
            )
            forecast.append({
                "date": str(forecast_date),
                "day_label": forecast_date.strftime("%a"),
                "weather": weather["state"],
                "icon": weather["icon"],
                "label": weather["label"],
                "description": weather["description"],
                "reasoning": weather["reasoning"],
            })

        # Store the forecast
        await db.execute(
            """INSERT INTO ecosystem_forecasts (site_id, forecast_date, forecast_data)
               VALUES ($1, $2, $3::jsonb)""",
            site_id, today, json.dumps(forecast),
        )

        return forecast

    def _calculate_trend(self, health_history: list) -> float:
        """Calculate trend direction from health history. Positive = improving."""
        if len(health_history) < 2:
            return 0.0

        scores = [float(row["score"]) for row in health_history if row["score"] is not None]
        if len(scores) < 2:
            return 0.0

        # Simple: compare recent average vs older average
        mid = len(scores) // 2
        recent_avg = sum(scores[:mid]) / mid if mid > 0 else 0
        older_avg = sum(scores[mid:]) / (len(scores) - mid) if (len(scores) - mid) > 0 else 0

        return recent_avg - older_avg

    def _predict_day(
        self,
        day_offset: int,
        trend_direction: float,
        decay_ratio: float,
        problem_ratio: float,
        is_weekend: bool,
    ) -> dict:
        """Predict weather for a single day."""

        # Base score from trend direction
        score = 0.5 + (trend_direction / 20.0)  # Normalize trend to 0-1 range

        # Decay ratio pushes toward rain/storm
        score -= decay_ratio * 0.3

        # Problem clusters push toward bad weather
        score -= problem_ratio * 0.2

        # Weekends tend to be calmer (less traffic, stable)
        if is_weekend:
            score = max(score, 0.35)  # At least cloudy on weekends

        # Future days have more uncertainty, tend toward cloudy
        score = score * (1 - day_offset * 0.05) + 0.5 * (day_offset * 0.05)

        # Clamp
        score = max(0.0, min(1.0, score))

        # Map score to weather state
        if score >= 0.7:
            state = "sunny"
            reasoning = "Health metrics are trending upward with strong cluster health."
        elif score >= 0.45:
            state = "cloudy"
            reasoning = "Metrics are stable. No significant changes expected."
        elif score >= 0.25:
            state = "rainy"
            reasoning = "Some content decay detected. Minor metric dips likely."
        else:
            state = "stormy"
            reasoning = "Significant content issues detected. Expect metric declines."

        if is_weekend:
            reasoning += " Weekend traffic patterns may reduce visibility."

        if day_offset > 4:
            reasoning += " Forecast confidence decreases with distance."

        return {
            "state": state,
            "icon": WEATHER_STATES[state]["icon"],
            "label": WEATHER_STATES[state]["label"],
            "description": WEATHER_STATES[state]["description"],
            "reasoning": reasoning,
        }
