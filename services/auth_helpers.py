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
    key = os.environ.get('SUPABASE_KEY', '') or os.environ.get('SUPABASE_SERVICE_KEY', '')
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


def signup(email: str, password: str) -> Dict[str, Any]:
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
        confirmed = bool(getattr(user, 'email_confirmed_at', None) or getattr(user, 'confirmed_at', None))
        # Profil satırını public.users'a ekle (idempotent)
        admin = _get_admin_client()
        if admin is not None:
            try:
                admin.table('users').upsert({
                    'id': user_id,
                    'email': email,
                    'created_at': datetime.now(timezone.utc).isoformat(),
                }, on_conflict='id').execute()
            except Exception as e:
                print(f'[Auth] users profile upsert failed (non-fatal): {e}')
        return {
            'ok': True, 'user_id': user_id, 'email': email,
            'requires_confirmation': not confirmed, 'error': None,
        }
    except Exception as e:
        msg = str(e)
        # Supabase 'User already registered' → mevcut hesap
        if 'already' in msg.lower() or 'registered' in msg.lower():
            return {'ok': False, 'error': 'EMAIL_EXISTS', 'user_id': None, 'email': email}
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
