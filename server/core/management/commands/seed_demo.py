"""Create a believable demo org: an admin, four developers, two weeks of cards, a briefing.

    python manage.py seed_demo            # adds demo data
    python manage.py seed_demo --reset    # wipes LearnLoop data + demo users first

Uses the offline mock agent so seeding is free and deterministic, even if an API key is set.
"""
import random
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.agent.analyzer import analyze
from core.agent.reporter import generate_report
from core.models import AnalyzeLog, Card, Concept, TeamReport, UserConcept
from core.services import knowledge
from core.services.accounts import create_member

User = get_user_model()
DEMO_DOMAIN = "demo.learnloop.dev"

SAMPLES = {
    "src/auth/jwt.ts": """+import jwt from "jsonwebtoken";
+export function issueTokens(userId: string) {
+  const accessToken = jwt.sign({ sub: userId }, process.env.JWT_SECRET!, { expiresIn: "15m" });
+  const refreshToken = crypto.randomUUID();
+  await db.refreshTokens.insert({ userId, token: refreshToken });
+  return { accessToken, refreshToken };
+}
+export async function rotate(oldRefreshToken: string) {
+  await db.refreshTokens.revoke(oldRefreshToken);
+  return issueTokens(owner.userId);
+}""",
    "src/auth/passwords.py": """+import bcrypt
+def hash_password(raw: str) -> bytes:
+    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt(rounds=12))
+def verify(raw: str, hashed: bytes) -> bool:
+    return bcrypt.checkpw(raw.encode(), hashed)""",
    "src/api/server.js": """+const rateLimit = require("express-rate-limit");
+app.use(rateLimit({ windowMs: 15 * 60 * 1000, max: 100 }));
+app.use(cors({ origin: ["https://app.example.com"] }));
+function requireAuth(req, res, next) { if (!req.user) return res.status(401).end(); next(); }""",
    "src/billing/payments.py": """+from django.db import transaction
+@transaction.atomic
+def charge(order):
+    order.mark_paid()
+    Ledger.objects.create(order=order, amount=order.total)
+    orders = Order.objects.select_related("customer").filter(paid=True)""",
    "web/src/components/Cart.tsx": """+import { useReducer, useEffect } from "react";
+function reducer(state, action) { switch (action.type) { case "add": return [...state, action.item]; default: return state; } }
+export function Cart() {
+  const [items, dispatch] = useReducer(reducer, []);
+  useEffect(() => { const id = setInterval(sync, 5000); return () => clearInterval(id); }, []);
+}""",
    "web/src/pages/Dashboard.tsx": """+const Chart = React.lazy(() => import("./Chart"));
+export default function Dashboard() {
+  return <Suspense fallback={<Spinner />}><Chart /></Suspense>;
+}
+.layout { display: grid; grid-template-columns: repeat(3, 1fr); }""",
    "infra/Dockerfile": """+FROM node:20 AS build
+RUN npm ci && npm run build
+FROM node:20-slim
+COPY --from=build /app/dist ./dist""",
    "tests/test_payments.py": """+import pytest
+from unittest.mock import patch
+@pytest.fixture
+def order(db): return OrderFactory()
+@patch("billing.gateway.charge")
+def test_charge(mock_charge, order): ...""",
}

PEOPLE = [
    ("ana", "Ana Krasniqi", "intermediate", ["src/auth/jwt.ts", "src/auth/passwords.py", "src/billing/payments.py", "infra/Dockerfile"], 0.8),
    ("ben", "Ben Hoxha", "beginner", ["src/auth/jwt.ts", "src/api/server.js", "web/src/components/Cart.tsx", "src/billing/payments.py"], 0.2),
    ("dea", "Dea Morina", "beginner", ["web/src/components/Cart.tsx", "web/src/pages/Dashboard.tsx", "src/auth/jwt.ts", "tests/test_payments.py"], 0.3),
    ("edi", "Edi Gashi", "intermediate", ["src/api/server.js", "src/billing/payments.py", "tests/test_payments.py", "infra/Dockerfile"], 0.5),
]


class Command(BaseCommand):
    help = "Seed a demo organisation with users, cards and a manager briefing."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true")
        parser.add_argument("--admin-email", default=f"admin@{DEMO_DOMAIN}")
        parser.add_argument("--password", default="learnloop-demo-2026")

    def handle(self, *args, **opts):
        random.seed(7)
        if opts["reset"]:
            for model in (Card, AnalyzeLog, UserConcept, TeamReport, Concept):
                model.objects.all().delete()
            User.objects.filter(email__endswith=DEMO_DOMAIN).delete()

        old_mock = settings.LEARNLOOP["MOCK_AI"]
        settings.LEARNLOOP["MOCK_AI"] = True
        try:
            self._seed(opts)
        finally:
            settings.LEARNLOOP["MOCK_AI"] = old_mock

    def _seed(self, opts):
        pw = opts["password"]
        if not User.objects.filter(username=opts["admin_email"]).exists():
            create_member(email=opts["admin_email"], full_name="Lead Engineer", is_admin=True, password=pw, must_change_password=False)
        tokens = {}
        now = timezone.now()
        for handle, name, skill, files, known_ratio in PEOPLE:
            email = f"{handle}@{DEMO_DOMAIN}"
            if User.objects.filter(username=email).exists():
                continue
            user, _, token = create_member(email=email, full_name=name, password=pw, skill_level=skill, must_change_password=False)
            tokens[email] = token
            profile = knowledge.get_profile(user)
            profile.daily_card_limit = 50
            profile.save()
            for n, path in enumerate(files):
                cards, _ = analyze(user, f"demo-{handle}-{n}", [{"file": path, "diff": SAMPLES[path]}])
                when = now - timedelta(days=random.randint(0, 13), hours=random.randint(0, 8))
                Card.objects.filter(pk__in=[c.pk for c in cards]).update(created_at=when, read_at=when if random.random() < 0.6 else None)
            for uc in UserConcept.objects.filter(user=user):
                if random.random() < known_ratio:
                    knowledge.set_status(user, uc.concept, UserConcept.Status.KNOWN)
            profile.daily_card_limit = 8
            profile.last_active_at = now - timedelta(days=random.randint(0, 3))
            profile.save()

        report = generate_report(days=14)
        self.stdout.write(self.style.SUCCESS("Demo org ready."))
        self.stdout.write(f"  Admin: {opts['admin_email']} / {pw}")
        self.stdout.write(f"  Members: ana|ben|dea|edi@{DEMO_DOMAIN} / {pw}")
        for email, token in tokens.items():
            self.stdout.write(f"  token {email}: {token}")
        self.stdout.write(f"  Briefing: {report.title}")
