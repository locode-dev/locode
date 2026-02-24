import json, logging, re, requests
log = logging.getLogger("refiner")

# Much broader type detection
SITE_TYPES = {
    "ecommerce":  ["shop","store","ecommerce","e-commerce","product","buy","sell","cart","retail","marketplace"],
    "portfolio":  ["portfolio","personal","resume","cv","my work","showcase my"],
    "saas":       ["saas","platform","dashboard","subscription","b2b","crm","analytics tool"],
    "restaurant": ["restaurant","food","cafe","menu","dining","eat","bistro","bar","coffee shop"],
    "blog":       ["blog","article","news","magazine","journal","writing","posts"],
    "agency":     ["agency","studio","creative","marketing","branding","advertising"],
    "startup":    ["startup","launch","mvp","venture","raise funding"],
    "corporate":  ["corporate","enterprise","consulting","b2b company","firm"],
    "landing":    ["landing page","waitlist","coming soon","pre-launch"],
    # NEW: broader app types
    "tool":       ["calculator","converter","timer","clock","weather","currency","unit","generator","checker"],
    "game":       ["game","quiz","puzzle","trivia","arcade","play","score","level","player"],
    "app":        ["app","application","tracker","manager","planner","organizer","notes","todo","habit"],
    "dashboard":  ["dashboard","admin","analytics","stats","metrics","monitor","chart","graph","data"],
    "social":     ["social","community","forum","chat","messaging","network","profile","feed"],
}

# Section maps for known types
SECTION_MAP = {
    "ecommerce":  ["Hero","FeaturedProducts","Categories","Testimonials","Newsletter"],
    "portfolio":  ["Hero","About","Skills","Projects","Contact"],
    "saas":       ["Hero","Features","HowItWorks","Pricing","Testimonials","CTA"],
    "restaurant": ["Hero","Menu","About","Gallery","Reservations"],
    "blog":       ["Hero","FeaturedPosts","Categories","Newsletter","Contact"],
    "agency":     ["Hero","Services","Work","Team","Contact"],
    "startup":    ["Hero","Problem","Solution","Features","Pricing","Contact"],
    "corporate":  ["Hero","About","Services","Team","Contact"],
    "landing":    ["Hero","Features","HowItWorks","Testimonials","CTA"],
    "tool":       ["App"],        # Single component — the tool itself
    "game":       ["App"],        # Single component — the game itself
    "app":        ["App"],        # Single component — the app itself
    "dashboard":  ["App"],        # Single component — the dashboard
    "social":     ["Hero","Feed","Profiles","Contact"],
    "general":    ["Hero","Features","About","Contact"],
}

# Builder strategy: "react-app" = single App component, "react-sections" = multi-section site
STRATEGY_MAP = {
    "tool": "react-app", "game": "react-app",
    "app":  "react-app", "dashboard": "react-app",
}

SYSTEM_PROMPT = (
    "You are a JSON API. Output ONLY a raw JSON object. No markdown, no explanation.\n\n"
    "Given a website/app idea, classify it and return exactly:\n"
    '{"project_name":"kebab-case","site_type":"ecommerce|portfolio|saas|restaurant|blog|agency|'
    'startup|corporate|landing|tool|game|app|dashboard|social|general",'
    '"title":"Title","tagline":"Catchphrase","description":"2-3 sentences",'
    '"color_scheme":"describe colors and theme","style":"modern|minimal|bold|playful|retro|corporate|luxury",'
    '"brand_name":"Brand or App Name","target_audience":"who this is for",'
    '"key_features":["feature1","feature2","feature3"],'
    '"special_instructions":"specific design, animation, content requirements"}\n\n'
    "site_type MUST be one of the listed values. Output ONLY JSON starting with {.\n"
    "CRITICAL: Do not suggest or include uninstalled third-party packages in 'special_instructions' "
    "(e.g. NEVER suggest react-scroll or react-icons/all, use window.scrollTo and react-icons/fi)."
)


class RefinerAgent:
    def __init__(self, ollama_url, model):
        self.url   = f"{ollama_url}/api/chat"
        self.model = model

    def refine(self, raw_idea):
        log.info(f"Refining idea with {self.model}...")
        site_type = self._detect_type(raw_idea)
        log.info(f"   Keyword-detected type: {site_type}")
        llm_data  = self._llm_refine(raw_idea)
        spec      = self._build_spec(raw_idea, site_type, llm_data)
        strategy  = STRATEGY_MAP.get(spec["site_type"], "react-sections")
        spec["strategy"] = strategy
        log.info(f"   Final: '{spec['title']}' | type={spec['site_type']} | strategy={strategy}")
        log.info(f"   Sections: {spec['sections']}")
        return json.dumps(spec, indent=2)

    def _detect_type(self, idea):
        il = idea.lower()
        for site_type, keywords in SITE_TYPES.items():
            if any(k in il for k in keywords):
                return site_type
        return "general"

    def _llm_refine(self, raw_idea):
        try:
            resp = requests.post(self.url, json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": f"Idea: {raw_idea}\n\nJSON only:"}
                ],
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 500}
            }, timeout=60)
            resp.raise_for_status()
            content = resp.json()["message"]["content"].strip()
            if "```" in content:
                parts = content.split("```")
                content = parts[1] if len(parts) > 1 else parts[0]
                if content.startswith("json"): content = content[4:]
            s, e = content.find("{"), content.rfind("}")
            if s != -1 and e != -1:
                return json.loads(content[s:e+1])
        except Exception as ex:
            log.warning(f"LLM refine failed ({ex}), using keyword detection")
        return {}

    def _build_spec(self, raw_idea, site_type, llm_data):
        # LLM type overrides keyword detection if valid
        llm_type = llm_data.get("site_type", "")
        final_type = llm_type if llm_type in SECTION_MAP else site_type
        if final_type not in SECTION_MAP:
            final_type = "general"

        brand = (llm_data.get("brand_name")
                 or llm_data.get("title")
                 or self._extract_name(raw_idea))

        project_name = re.sub(r'[^a-z0-9]+', '-', brand.lower())[:30].strip('-')

        return {
            "project_name":         project_name,
            "site_type":            final_type,
            "strategy":             STRATEGY_MAP.get(final_type, "react-sections"),
            "title":                llm_data.get("title", brand),
            "tagline":              llm_data.get("tagline", f"Welcome to {brand}"),
            "description":          llm_data.get("description", raw_idea[:300]),
            "color_scheme":         llm_data.get("color_scheme", "dark with cyan and purple accents"),
            "style":                llm_data.get("style", "modern"),
            "brand_name":           brand,
            "target_audience":      llm_data.get("target_audience", "Everyone"),
            "key_features":         llm_data.get("key_features", []),
            "special_instructions": llm_data.get("special_instructions", raw_idea),
            "sections":             SECTION_MAP.get(final_type, SECTION_MAP["general"]),
            # Legacy keys
            "design": {
                "style":        llm_data.get("style", "modern"),
                "color_scheme": llm_data.get("color_scheme", "dark with cyan and purple accents"),
            },
            "features": llm_data.get("key_features", []),
        }

    def _extract_name(self, idea):
        stop = {"a","an","the","build","create","make","i","want","need",
                "with","for","and","or","of","website","site","page","web","app"}
        words = [w.strip(".,!?") for w in idea.split() if w.lower() not in stop]
        return " ".join(words[:3]).title() if words else "My App"