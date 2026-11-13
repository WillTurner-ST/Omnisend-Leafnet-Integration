import logging
from typing import Optional, Dict, Any, List
from middleware.clients.leafnet_client import LeafnetClient
from middleware.clients.omnisend_client import OmnisendClient
from middleware.models.leafnet import (
    LoyaltyLookupResponse,
    LoyaltyRedeemResponse,
)
from middleware.models.omnisend import OmnisendEventPayload

logger = logging.getLogger("middleware.loyalty_service")


class LoyaltyService:
    # Loyalty Milestones and reward details (mirroring Marsello tiers + extensible future tiers)
    MILESTONES = [
        {"threshold": 100.0, "name": "100 Points Milestone", "reward": "$5 off", "discount_code": "REWARD5OFF"},
        {"threshold": 200.0, "name": "200 Points Milestone", "reward": "10% off", "discount_code": "REWARD10PCT"},
        {"threshold": 300.0, "name": "300 Points Milestone", "reward": "$15 off", "discount_code": "REWARD15OFF"},
        {"threshold": 500.0, "name": "500 Points Milestone", "reward": "25% off", "discount_code": "REWARD25PCT"},
    ]

    def __init__(
        self,
        leafnet_client: Optional[LeafnetClient] = None,
        omnisend_client: Optional[OmnisendClient] = None,
    ):
        self.leafnet = leafnet_client or LeafnetClient()
        self.omnisend = omnisend_client or OmnisendClient()

    @classmethod
    def highest_reached_threshold(cls, points: float) -> float:
        """Highest milestone the customer has already passed, or 0."""
        reached = 0.0
        for ms in cls.MILESTONES:
            if points >= ms["threshold"]:
                reached = ms["threshold"]
        return reached

    @classmethod
    def get_milestone_progress(cls, points: float) -> Dict[str, Any]:
        """
        Calculates current loyalty tier and points needed for next milestone
        so Omnisend emails can display dynamic loyalty progress banners.
        """
        current_tier = "Member"
        current_reward = "None"
        next_threshold = cls.MILESTONES[0]["threshold"]
        next_reward = cls.MILESTONES[0]["reward"]

        for i, ms in enumerate(cls.MILESTONES):
            if points >= ms["threshold"]:
                current_tier = ms["name"]
                current_reward = ms["reward"]
                if i + 1 < len(cls.MILESTONES):
                    next_threshold = cls.MILESTONES[i + 1]["threshold"]
                    next_reward = cls.MILESTONES[i + 1]["reward"]
                else:
                    next_threshold = ms["threshold"]
                    next_reward = ms["reward"]
            else:
                next_threshold = ms["threshold"]
                next_reward = ms["reward"]
                break

        points_needed = max(0.0, round(next_threshold - points, 2))
        return {
            "loyalty_tier_name": current_tier,
            "available_reward": current_reward,
            "next_milestone_points": next_threshold,
            "next_milestone_reward": next_reward,
            "points_to_next_milestone": points_needed,
        }

    async def get_loyalty_balance(self, phone: str, get_history: bool = True) -> LoyaltyLookupResponse:
        """Looks up a customer's loyalty balance and points history from Leafnet."""
        return await self.leafnet.loyalty_lookup(phone=phone, get_history=get_history)

    async def redeem_reward(
        self,
        phone: str,
        points: float,
        description: str,
        order_id: str,
        discount_id: Optional[str] = None,
        location_code: Optional[str] = None,
    ) -> LoyaltyRedeemResponse:
        """
        Redeems points in Leafnet when a customer applies their loyalty milestone coupon at register.
        """
        res = await self.leafnet.loyalty_redeem(
            phone=phone,
            points=points,
            description=description,
            order_id=order_id,
            discount_id=discount_id,
            location_code=location_code,
        )

        # Trigger event in Omnisend if customer email is available
        try:
            lookup = await self.leafnet.loyalty_lookup(phone=phone, get_history=False)
            if lookup.email:
                event = OmnisendEventPayload(
                    eventName="Loyalty Points Redeemed",
                    email=lookup.email,
                    phone=phone,
                    eventID=f"loyalty-redeem-{order_id}-{int(points)}",
                    properties={
                        "points_redeemed": points,
                        "points_remaining": res.points_remaining,
                        "description": description,
                        "order_id": order_id,
                        "discount_id": discount_id or "",
                        "location": location_code or "",
                    },
                )
                await self.omnisend.trigger_event(event)
        except Exception as e:
            logger.warning(f"Could not trigger loyalty redeem event in Omnisend: {e}")

        return res

    async def check_and_trigger_milestones(
        self,
        email: str,
        phone: Optional[str],
        points: float,
        previous_points: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        Checks if customer crossed a milestone threshold (e.g. 100 or 200 points).
        If crossed, triggers Omnisend milestone event to issue reward email.
        """
        triggered: List[Dict[str, Any]] = []
        for ms in self.MILESTONES:
            threshold = ms["threshold"]
            if previous_points < threshold <= points:
                logger.info(f"Customer {email} crossed milestone {threshold} pts ({ms['reward']})!")
                event = OmnisendEventPayload(
                    eventName="Loyalty Milestone Reached",
                    email=email,
                    phone=phone,
                    eventID=f"milestone-{int(threshold)}-{email}",
                    properties={
                        "milestone_name": ms["name"],
                        "points_threshold": threshold,
                        "points_balance": points,
                        "reward": ms["reward"],
                        "discount_code": ms["discount_code"],
                    },
                )
                try:
                    await self.omnisend.trigger_event(event)
                    triggered.append(ms)
                except Exception as e:
                    logger.warning(f"Failed to trigger milestone event for {email}: {e}")

        return triggered
