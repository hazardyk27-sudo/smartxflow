"""
Supabase Auth helper — Task #181 (Google Play Faz 1)

Risk-free additive: bu modül mevcut hiçbir koda dokunmaz. Sadece yeni
auth endpoint'lerinden ve account-deletion scheduler'dan çağrılır.

Supabase Python SDK 2.28.0 kullanır:
    supabase.auth.sign_up({email, password})
    supabase.auth.sign_in_with_password({email, password})
    supabase.auth.get_user(jwt)
    supabase.auth.admin.delete_user(user_id)  # service_role gerekli
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
    Client = None

_anon_client = None
_admin_client = None


def _get_anon_client():
    """Supabase client with ANON_KEY — signup/login/get_user için."""
    global _anon_client
    if _anon_client is not None:
        return _anon_client
    if create_client is None:
        return None
    url = os.environ.get('SUPABASE_URL', '')
    key = os.environ.get('SUPABASE_ANON_KEY', '')
    if not url or not key:
        print('[Auth] SUPABASE_URL or SUPABASE_ANON_KEY missing — auth disabled')
        return None
    try:
        _anon_client = create_client(url, key)
        return _anon_client
    except Exception as e:
        print(f'[Auth] Anon client init failed: {e}')
        return None


def _get_admin_client():
    """Supabase client with SERVICE_ROLE — admin.delete_user, table writes için."""
    global _admin_client
    if _admin_client is not None:
        return _admin_client
    if create_client is None:
        return None
    url = os.environ.get('SUPABASE_URL', '')
    key = (os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
           or os.environ.get('SUPABASE_KEY', '')
           or os.environ.get('SUPABASE_SERVICE_KEY', ''))
    if not url or not key:
        print('[Auth] SUPABASE_URL or SUPABASE_KEY (service_role) missing — admin ops disabled')
        return None
    try:
        _admin_client = create_client(url, key)
        return _admin_client
    except Exception as e:
        print(f'[Auth] Admin client init failed: {e}')
        return None


def is_auth_available() -> bool:
    """True if Supabase Auth is configured and reachable."""
    return _get_anon_client() is not None


def signup(email: str, password: str, display_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Yeni kullanıcı kaydı. Supabase Auth'a kayıt + public.users tablosuna profil ekler.
    Returns: {ok: bool, user_id: str|None, email: str, error: str|None, requires_confirmation: bool}
    """
    email = (email or '').strip().lower()
    if not email or '@' not in email:
        return {'ok': False, 'error': 'INVALID_EMAIL', 'user_id': None, 'email': email}
    if not password or len(password) < 8:
        return {'ok': False, 'error': 'PASSWORD_TOO_SHORT', 'user_id': None, 'email': email}
    client = _get_anon_client()
    if client is None:
        return {'ok': False, 'error': 'AUTH_UNAVAILABLE', 'user_id': None, 'email': email}
    try:
        resp = client.auth.sign_up({'email': email, 'password': password})
        user = getattr(resp, 'user', None)
        if user is None:
            return {'ok': False, 'error': 'SIGNUP_FAILED', 'user_id': None, 'email': email}
        user_id = user.id
        # Supabase silently "succeeds" sign_up for an already-registered email
        # (to avoid leaking which emails exist) but returns an empty identities list.
        identities = getattr(user, 'identities', None)
        if identities is not None and len(identities) == 0:
            return {'ok': False, 'error': 'EMAIL_ALREADY_REGISTERED', 'user_id': None, 'email': email}
        confirmed = bool(getattr(user, 'email_confirmed_at', None) or getattr(user, 'confirmed_at', None))
        # Profil satırını public.users'a ekle (idempotent — DB trigger da ekler, burada garanti altına aliniyor)
        admin = _get_admin_client()
        if admin is not None:
            try:
                row = {'id': user_id, 'email': email}
                if display_name:
                    row['display_name'] = display_name
                admin.table('users').upsert(row, on_conflict='id').execute()
            except Exception as e:
                print(f'[Auth] users profile upsert failed (non-fatal): {e}')
        return {
            'ok': True, 'user_id': user_id, 'email': email,
            'requires_confirmation': not confirmed, 'error': None,
        }
    except Exception as e:
        msg = str(e)
        if 'already' in msg.lower() or 'registered' in msg.lower():
            return {'ok': False, 'error': 'EMAIL_ALREADY_REGISTERED', 'user_id': None, 'email': email}
        if 'weak' in msg.lower() or 'password' in msg.lower():
            return {'ok': False, 'error': 'PASSWORD_TOO_WEAK', 'user_id': None, 'email': email}
        print(f'[Auth] signup error: {e}')
        return {'ok': False, 'error': 'SIGNUP_FAILED', 'user_id': None, 'email': email, 'detail': msg[:200]}


def login(email: str, password: str) -> Dict[str, Any]:
    """
    Email/şifre ile giriş.
    Returns: {ok: bool, user_id: str|None, email: str, access_token: str|None, error: str|None}
    """
    email = (email or '').strip().lower()
    if not email or not password:
        return {'ok': False, 'error': 'MISSING_CREDENTIALS', 'user_id': None, 'email': email}
    client = _get_anon_client()
    if client is None:
        return {'ok': False, 'error': 'AUTH_UNAVAILABLE', 'user_id': None, 'email': email}
    try:
        resp = client.auth.sign_in_with_password({'email': email, 'password': password})
        user = getattr(resp, 'user', None)
        session = getattr(resp, 'session', None)
        if user is None or session is None:
            return {'ok': False, 'error': 'INVALID_CREDENTIALS', 'user_id': None, 'email': email}
        # Soft-deleted kullanıcı kontrolü
        admin = _get_admin_client()
        if admin is not None:
            try:
                row = admin.table('users').select('deleted_at').eq('id', user.id).limit(1).execute()
                if row.data and row.data[0].get('deleted_at'):
                    return {'ok': False, 'error': 'ACCOUNT_DELETED', 'user_id': None, 'email': email}
            except Exception as e:
                print(f'[Auth] login deleted_at check failed (non-fatal): {e}')
        return {
            'ok': True, 'user_id': user.id, 'email': user.email or email,
            'access_token': session.access_token, 'refresh_token': session.refresh_token,
            'error': None,
        }
    except Exception as e:
        msg = str(e).lower()
        if 'invalid' in msg or 'credentials' in msg:
            return {'ok': False, 'error': 'INVALID_CREDENTIALS', 'user_id': None, 'email': email}
        print(f'[Auth] login error: {e}')
        return {'ok': False, 'error': 'LOGIN_FAILED', 'user_id': None, 'email': email}


def sign_out(access_token: str, refresh_token: str) -> None:
    """Supabase tarafinda refresh token'i gecersiz kilar (best-effort)."""
    client = _get_anon_client()
    if client is None or not access_token:
        return
    try:
        client.auth.set_session(access_token, refresh_token or '')
        client.auth.sign_out()
    except Exception as e:
        print(f'[Auth] sign_out error (non-fatal): {e}')


def get_user_from_token(access_token: str) -> Optional[Dict[str, Any]]:
    """
    Bir access token'in gecerli bir Supabase oturumuna ait olup olmadigini dogrular.
    Returns: {id, email, email_confirmed} or None if invalid/expired.
    """
    if not access_token:
        return None
    client = _get_anon_client()
    if client is None:
        return None
    try:
        resp = client.auth.get_user(access_token)
        user = getattr(resp, 'user', None)
        if user is None:
            return None
        confirmed = bool(getattr(user, 'email_confirmed_at', None) or getattr(user, 'confirmed_at', None))
        return {'id': user.id, 'email': user.email, 'email_confirmed': confirmed}
    except Exception:
        return None


def refresh_session(refresh_token: str) -> Dict[str, Any]:
    """Refresh token ile yeni access/refresh token cifti alir."""
    if not refresh_token:
        return {'ok': False, 'error': 'MISSING_REFRESH_TOKEN'}
    client = _get_anon_client()
    if client is None:
        return {'ok': False, 'error': 'AUTH_UNAVAILABLE'}
    try:
        resp = client.auth.refresh_session(refresh_token)
        session = getattr(resp, 'session', None)
        if session is None:
            return {'ok': False, 'error': 'REFRESH_FAILED'}
        return {'ok': True, 'access_token': session.access_token, 'refresh_token': session.refresh_token}
    except Exception as e:
        print(f'[Auth] refresh_session error: {e}')
        return {'ok': False, 'error': 'REFRESH_FAILED'}


def get_or_create_profile(user_id: str, email: str) -> Optional[Dict[str, Any]]:
    """
    public.users profil satirini getirir; yoksa (trigger henuz calismamis/gecikmisse)
    idempotent olarak olusturur. Returns the profile dict or None on hard failure.
    """
    if not user_id:
        return None
    admin = _get_admin_client()
    if admin is None:
        return None
    try:
        resp = admin.table('users').select('*').eq('id', user_id).limit(1).execute()
        if resp.data:
            return resp.data[0]
        ins = admin.table('users').upsert({
            'id': user_id,
            'email': (email or '').strip().lower(),
            'plan': 'core',
            'subscription_status': 'inactive',
        }, on_conflict='id').execute()
        if ins.data:
            return ins.data[0]
        resp2 = admin.table('users').select('*').eq('id', user_id).limit(1).execute()
        return resp2.data[0] if resp2.data else None
    except Exception as e:
        print(f'[Auth] get_or_create_profile error: {e}')
        return None


def is_membership_active(profile: Optional[Dict[str, Any]]) -> bool:
    """Uyelik durumu odemeli ozelliklere erisime izin veriyor mu?"""
    if not profile:
        return False
    status = (profile.get('subscription_status') or '').lower()
    if status not in ('active', 'trial'):
        return False
    expires_at = profile.get('subscription_expires_at')
    if expires_at:
        try:
            exp = datetime.fromisoformat(str(expires_at).replace('Z', '+00:00'))
            now = datetime.now(timezone.utc) if exp.tzinfo else datetime.utcnow()
            if exp < now:
                return False
        except Exception:
            pass
    return True


def update_membership(user_id: str, plan: Optional[str] = None, status: Optional[str] = None,
                       expires_at: Optional[str] = None, started_at: Optional[str] = None) -> Dict[str, Any]:
    """Admin/backend-only: bir kullanicinin plan/uyelik durumunu gunceller (service_role)."""
    if not user_id:
        return {'ok': False, 'error': 'MISSING_USER_ID'}
    admin = _get_admin_client()
    if admin is None:
        return {'ok': False, 'error': 'DB_UNAVAILABLE'}
    update_data = {}
    if plan is not None:
        update_data['plan'] = plan
    if status is not None:
        update_data['subscription_status'] = status
    if expires_at is not None:
        update_data['subscription_expires_at'] = expires_at
    if started_at is not None:
        update_data['subscription_started_at'] = started_at
    if not update_data:
        return {'ok': False, 'error': 'NOTHING_TO_UPDATE'}
    try:
        admin.table('users').update(update_data).eq('id', user_id).execute()
        return {'ok': True}
    except Exception as e:
        print(f'[Auth] update_membership error: {e}')
        return {'ok': False, 'error': 'UPDATE_FAILED'}


def find_profile_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Admin panel icin: e-posta ile profil arar."""
    admin = _get_admin_client()
    if admin is None or not email:
        return None
    try:
        resp = admin.table('users').select('*').eq('email', email.strip().lower()).limit(1).execute()
        return resp.data[0] if resp.data else None
    except Exception as e:
        print(f'[Auth] find_profile_by_email error: {e}')
        return None


def resend_verification_email(email: str) -> Dict[str, Any]:
    """Dogrulama e-postasini yeniden gonderir (yeni gecerli token uretir)."""
    client = _get_anon_client()
    if client is None:
        return {'ok': False, 'error': 'AUTH_UNAVAILABLE'}
    try:
        client.auth.resend({'type': 'signup', 'email': (email or '').strip().lower()})
        return {'ok': True}
    except Exception as e:
        print(f'[Auth] resend_verification_email error: {e}')
        return {'ok': False, 'error': 'RESEND_FAILED'}


def send_password_reset(email: str, redirect_to: str) -> Dict[str, Any]:
    """Sifre sifirlama e-postasi gonderir."""
    client = _get_anon_client()
    if client is None:
        return {'ok': False, 'error': 'AUTH_UNAVAILABLE'}
    try:
        client.auth.reset_password_email((email or '').strip().lower(), {'redirect_to': redirect_to})
        return {'ok': True}
    except Exception as e:
        print(f'[Auth] send_password_reset error: {e}')
        return {'ok': False, 'error': 'RESET_EMAIL_FAILED'}


def update_password_with_session(access_token: str, refresh_token: str, new_password: str) -> Dict[str, Any]:
    """Recovery/oturum tokenlariyla sifreyi gunceller (forgot-password akisi)."""
    if not new_password or len(new_password) < 8:
        return {'ok': False, 'error': 'PASSWORD_TOO_SHORT'}
    client = _get_anon_client()
    if client is None:
        return {'ok': False, 'error': 'AUTH_UNAVAILABLE'}
    try:
        client.auth.set_session(access_token, refresh_token or '')
        client.auth.update_user({'password': new_password})
        return {'ok': True}
    except Exception as e:
        print(f'[Auth] update_password_with_session error: {e}')
        return {'ok': False, 'error': 'UPDATE_PASSWORD_FAILED'}


def migrate_license_to_account(license_key: str, email: str, password: str) -> Dict[str, Any]:
    """
    Mevcut (aktif) lisans anahtarini yeni bir email/sifre hesabina tasir:
    1) key gecerli mi + daha once migrate edilmemis mi kontrol eder
    2) yeni Supabase Auth hesabi olusturur
    3) profildeki plan/uyelik alanlarini lisanstan kopyalar
    4) lisansi migrated olarak isaretler (tekrar kullanilamaz)
    """
    license_key = (license_key or '').strip()
    if not license_key:
        return {'ok': False, 'error': 'MISSING_LICENSE_KEY'}
    admin = _get_admin_client()
    if admin is None:
        return {'ok': False, 'error': 'DB_UNAVAILABLE'}
    try:
        lic_resp = admin.table('licenses').select('*').eq('key', license_key).limit(1).execute()
        if not lic_resp.data:
            return {'ok': False, 'error': 'LICENSE_NOT_FOUND'}
        lic = lic_resp.data[0]
        if lic.get('status') == 'revoked':
            return {'ok': False, 'error': 'LICENSE_REVOKED'}
        if lic.get('migrated_to_user_id'):
            return {'ok': False, 'error': 'LICENSE_ALREADY_MIGRATED'}
        expires_at = lic.get('expires_at')
        if expires_at:
            try:
                exp_dt = datetime.fromisoformat(str(expires_at).replace('Z', '+00:00'))
                now = datetime.now(timezone.utc) if exp_dt.tzinfo else datetime.utcnow()
                if exp_dt < now:
                    return {'ok': False, 'error': 'LICENSE_EXPIRED'}
            except Exception:
                pass
    except Exception as e:
        print(f'[Auth] migrate_license_to_account lookup error: {e}')
        return {'ok': False, 'error': 'LOOKUP_FAILED'}

    signup_result = signup(email, password)
    if not signup_result.get('ok'):
        return signup_result

    user_id = signup_result['user_id']
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        admin.table('users').update({
            'plan': lic.get('plan') or 'core',
            'subscription_status': 'active',
            'subscription_started_at': now_iso,
            'subscription_expires_at': lic.get('expires_at'),
            'migrated_from_license': license_key,
        }).eq('id', user_id).execute()
        admin.table('licenses').update({
            'migrated_to_user_id': user_id,
            'migrated_at': now_iso,
        }).eq('key', license_key).execute()
    except Exception as e:
        print(f'[Auth] migrate_license_to_account apply error: {e}')
        return {'ok': False, 'error': 'MIGRATION_APPLY_FAILED', 'user_id': user_id}

    return {
        'ok': True,
        'user_id': user_id,
        'email': signup_result['email'],
        'requires_confirmation': signup_result.get('requires_confirmation', True),
    }


def get_user_active_license(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Kullanıcının aktif (revoke edilmemiş, süresi geçmemiş) lisansını döner.
    Returns: {key, plan, expires_at, status} or None.
    """
    if not user_id:
        return None
    admin = _get_admin_client()
    if admin is None:
        return None
    try:
        resp = (admin.table('licenses')
                .select('key,plan,expires_at,status')
                .eq('user_id', user_id)
                .eq('status', 'active')
                .order('expires_at', desc=True)
                .limit(1)
                .execute())
        if resp.data:
            return resp.data[0]
    except Exception as e:
        print(f'[Auth] get_user_active_license error: {e}')
    return None


def bind_license_to_user(user_id: str, license_key: str) -> Dict[str, Any]:
    """
    Mevcut lisans key'ini kullanıcı hesabına bağlar.
    Aynı key başka user'a bağlıysa hata döner.
    """
    if not user_id or not license_key:
        return {'ok': False, 'error': 'MISSING_PARAMS'}
    admin = _get_admin_client()
    if admin is None:
        return {'ok': False, 'error': 'DB_UNAVAILABLE'}
    try:
        cur = admin.table('licenses').select('key,user_id,status').eq('key', license_key).limit(1).execute()
        if not cur.data:
            return {'ok': False, 'error': 'LICENSE_NOT_FOUND'}
        row = cur.data[0]
        if row.get('status') == 'revoked':
            return {'ok': False, 'error': 'LICENSE_REVOKED'}
        existing_uid = row.get('user_id')
        if existing_uid and existing_uid != user_id:
            return {'ok': False, 'error': 'LICENSE_ALREADY_BOUND'}
        if existing_uid == user_id:
            return {'ok': True, 'already_bound': True}
        admin.table('licenses').update({'user_id': user_id}).eq('key', license_key).execute()
        return {'ok': True, 'already_bound': False}
    except Exception as e:
        print(f'[Auth] bind_license_to_user error: {e}')
        return {'ok': False, 'error': 'BIND_FAILED'}


def request_account_deletion(user_id: str, email: str, retention_days: int = 30) -> Dict[str, Any]:
    """
    Soft delete: users.deleted_at set + queue tablosuna 30 gün sonra hard delete planı.
    Hesabın lisansı pasif kalır (status='cancelled' yapılır).
    """
    if not user_id:
        return {'ok': False, 'error': 'MISSING_USER_ID'}
    admin = _get_admin_client()
    if admin is None:
        return {'ok': False, 'error': 'DB_UNAVAILABLE'}
    now = datetime.now(timezone.utc)
    hard_after = now + timedelta(days=retention_days)
    try:
        admin.table('users').update({
            'deleted_at': now.isoformat(),
            'hard_delete_after': hard_after.isoformat(),
        }).eq('id', user_id).execute()
        admin.table('account_deletion_queue').insert({
            'user_id': user_id,
            'email': email or '',
            'scheduled_hard_delete_at': hard_after.isoformat(),
            'notes': 'User-requested deletion (Google Play compliance)',
        }).execute()
        # Aktif lisansı 'cancelled' yap (hard delete'te zaten silinecek ama erişimi keser)
        try:
            admin.table('licenses').update({'status': 'cancelled'}).eq('user_id', user_id).eq('status', 'active').execute()
        except Exception as e:
            print(f'[Auth] cancel licenses (non-fatal): {e}')
        return {'ok': True, 'hard_delete_after': hard_after.isoformat()}
    except Exception as e:
        print(f'[Auth] request_account_deletion error: {e}')
        return {'ok': False, 'error': 'DELETE_REQUEST_FAILED'}


def cancel_account_deletion(user_id: str) -> Dict[str, Any]:
    """Eğer 30 gün dolmamışsa silme talebini iptal eder."""
    admin = _get_admin_client()
    if admin is None:
        return {'ok': False, 'error': 'DB_UNAVAILABLE'}
    try:
        admin.table('users').update({
            'deleted_at': None, 'hard_delete_after': None,
        }).eq('id', user_id).execute()
        now = datetime.now(timezone.utc).isoformat()
        admin.table('account_deletion_queue').update({'cancelled_at': now}).eq('user_id', user_id).is_('completed_at', 'null').is_('cancelled_at', 'null').execute()
        return {'ok': True}
    except Exception as e:
        print(f'[Auth] cancel_account_deletion error: {e}')
        return {'ok': False, 'error': 'CANCEL_FAILED'}


def get_pending_hard_deletes() -> List[Dict[str, Any]]:
    """30 günü doldurmuş, henüz hard-delete edilmemiş hesapları döner."""
    admin = _get_admin_client()
    if admin is None:
        return []
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        resp = (admin.table('account_deletion_queue')
                .select('id,user_id,email,scheduled_hard_delete_at')
                .lte('scheduled_hard_delete_at', now_iso)
                .is_('completed_at', 'null')
                .is_('cancelled_at', 'null')
                .limit(50)
                .execute())
        return resp.data or []
    except Exception as e:
        print(f'[Auth] get_pending_hard_deletes error: {e}')
        return []


def hard_delete_user(user_id: str, queue_id: int) -> bool:
    """Bir kullanıcıyı kalıcı olarak siler (Supabase Auth + public.users + lisans bağı koparılır)."""
    admin = _get_admin_client()
    if admin is None:
        return False
    try:
        # 1) Lisansları user_id=NULL yap (lisansların kendisi silinmesin, kayıt olarak kalsın)
        try:
            admin.table('licenses').update({'user_id': None}).eq('user_id', user_id).execute()
        except Exception as e:
            print(f'[Auth] hard_delete licenses unlink (non-fatal): {e}')
        # 2) public.users sil
        try:
            admin.table('users').delete().eq('id', user_id).execute()
        except Exception as e:
            print(f'[Auth] hard_delete users (non-fatal): {e}')
        # 3) Supabase auth.users sil (admin API)
        try:
            admin.auth.admin.delete_user(user_id)
        except Exception as e:
            print(f'[Auth] hard_delete auth.users error: {e}')
            return False
        # 4) Queue'yu completed işaretle
        try:
            admin.table('account_deletion_queue').update({
                'completed_at': datetime.now(timezone.utc).isoformat(),
            }).eq('id', queue_id).execute()
        except Exception as e:
            print(f'[Auth] hard_delete queue update (non-fatal): {e}')
        print(f'[Auth] Hard-deleted user {user_id} (queue #{queue_id})')
        return True
    except Exception as e:
        print(f'[Auth] hard_delete_user fatal: {e}')
        return False
