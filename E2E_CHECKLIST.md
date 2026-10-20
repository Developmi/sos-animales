# E2E Checklist — SOS Animales

**App**: FastAPI + HTMX + Pico.css + PostgreSQL  
**URL**: http://localhost:9494  
**Browser**: Chromium (Playwright MCP)

---

## 1. 🌐 Landing & Legal Pages

- [ ] `GET /` — Home page loads with full layout (nav, footer, content)
- [ ] `GET /legal/privacy` — Privacy policy renders
- [ ] `GET /legal/cookies` — Cookies policy renders
- [ ] `GET /legal/terms` — Terms of service render
- [ ] `GET /legal/data-processing` — Data processing consent renders
- [ ] `GET /api/ping-htmx` — Diagnostic HTMX fragment responds OK

## 2. 🏢 Sources (Shelters & Organizations)

- [ ] `GET /sources/register` — Self-registration form renders
- [ ] `POST /sources/register` — Successful registration → confirmation message
- [ ] `GET /sources` — Directory of active sources loads
- [ ] `GET /sources?municipality=...` — Filter by municipality works
- [ ] `GET /sources/{id}` — Source profile loads with campaigns and animals

## 3. 💉 Sterilization (Campaigns & Fixed Points)

- [ ] `GET /sterilization/` — Main map page loads
- [ ] `GET /sterilization/search` — Search by municipality/species works
- [ ] `GET /sterilization/campaigns` — Campaigns list loads
- [ ] `GET /sterilization/campaigns/{id}` — Campaign detail view loads
- [ ] `GET /sterilization/fixed-points/new` — Fixed point form loads
- [ ] `POST /sterilization/fixed-points/new` — Fixed point creation succeeds
- [ ] `GET /sterilization/department-options` — Department select options load
- [ ] `GET /sterilization/municipality-options` — Municipality select options load
- [ ] `POST /sterilization/confirm/{entity_type}/{entity_id}` — Confirming entity updates last_confirmed_at

## 4. 🐾 Animals (Adoption Catalog)

- [ ] `GET /animals/` — Base adoption search landing page loads
- [ ] `GET /animals/list` — Profile grid loads
- [ ] `GET /animals/list?municipality=...&species=...` — Combined search filters work
- [ ] `GET /animals/new` — Profile submission form loads
- [ ] `POST /animals/` — Profile creation succeeds (generates PIN)
- [ ] `GET /animals/{id}` — Profile detail loads
- [ ] `POST /animals/{id}/adopt` — Adoption with correct PIN succeeds
- [ ] `POST /animals/{id}/adopt` — Incorrect PIN displays error

## 5. ✅ Verification (Auditing)

- [ ] `POST /verification/request` — Verification request succeeds
- [ ] `GET /verification/visits/{id}/checklist` — Checklist form loads
- [ ] `POST /verification/visits/{id}/checklist` — Checklist evaluation processed

## 6. 👥 Community (Decentralized Reports)

- [ ] `GET /community/update` — Community update form loads
- [ ] `POST /community/update` — Community report created
- [ ] `POST /community/{update_id}/vote` — Community vote registered
- [ ] `GET /community/list` — Community updates list loads

## 7. 🧪 Edge Cases & Error Handling

- [ ] **404 page**: Non-existent route → custom 404 template
- [ ] **500 page**: Simulated error → custom 500 template
- [ ] **Empty state**: Empty search results display friendly empty state message
- [ ] **Form validation**: Required fields trigger validation errors if omitted
- [ ] **Municipality options**: Displays all departments and municipalities

## 8. 📊 Seed Data Verification

- [ ] Departments seeded (33 expected)
- [ ] Municipalities seeded (1123 expected)
- [ ] Seed campaign records present
- [ ] Seed animal profiles present

---

**Progress**: 0/40  
**Started**: —  
**Completed**: —
