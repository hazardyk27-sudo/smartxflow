---
name: Supabase plan and timeout root cause
description: Supabase PRO hesap; timeout hatalarının gerçek nedeni ve uygulanan fix
---

## Kural
Supabase hesabı **PRO** plandır. Free tier limitleri geçerli değildir.

**Why:** Kullanıcı 2026-06-20 tarihinde belirtti.

## Timeout (57014) Root Cause
`statement timeout` hataları plan limitinden değil, `get_matches_paginated` Phase 2'sinin **268 eşzamanlı bireysel Supabase sorgusu** açmasından kaynaklanıyordu (max_workers=20, remaining_hashes=268).

**Fix (2026-06-20):** Phase 2 tamamen kaldırıldı (`services/supabase_client.py` ~satır 963). Phase 1 batch'te bulunamayan maçlar boş odds ile gösterilir.
