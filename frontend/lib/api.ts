import axios from 'axios';

const api = axios.create({
    baseURL: '/api', // Proxied to backend via next.config.mjs
    withCredentials: true, // Important for session cookies (Auth)
});

// Robust way to get Telegram Init Data
export const getTMAInitData = (): string | null => {
    if (typeof window === 'undefined') return null;
    
    // 1. Try official WebApp object
    const fromWebApp = (window as any).Telegram?.WebApp?.initData;
    if (fromWebApp && fromWebApp.length > 0) return fromWebApp;
    
    // 2. Try URL hash (common in TDesktop and first load)
    const hash = window.location.hash;
    if (hash) {
        // Handle both #tgWebAppData=... and direct query params in hash
        const hashParams = new URLSearchParams(hash.startsWith('#') ? hash.substring(1) : hash);
        const tgData = hashParams.get('tgWebAppData');
        if (tgData) return tgData;
    }
    
    return null;
};

// Add TMA initData to headers if available
api.interceptors.request.use((config) => {
    const initData = getTMAInitData();
    if (initData) {
        config.headers['X-Telegram-Init-Data'] = initData;
    }
    return config;
});

export interface AdminSettings {
    public_log_enabled: boolean;
    public_log_channel_id: string;
    public_log_thread_id: string;
    verification_code: string;
}

export interface BackupFile {
    name: string;
    size_mb: number;
    mtime: number;
}

// --- INIT DATA ---
export interface InitData {
    user: UserData | null;
    classes: Record<string, [string, string, string]>;
    queue_types: { id: number; name: string; description?: string }[];
    last_updated: string;
    bot_username: string;
}

export interface UserData {
    id: number;
    telegram_id: number;
    username: string;
    avatar_url?: string;
    is_master: boolean;
    is_banned: boolean;
    main_role_id: number | null;
}

export const fetchInitData = async (): Promise<InitData> => {
    const { data } = await api.get<InitData>('/dashboard/init');
    return data;
};

export const loginViaTMA = async (initData: string): Promise<void> => {
    await api.post('/login', { initData });
};

// --- KH TABLE DATA ---
export interface KHTableRow {
    role_id: number;
    name: string;
    class_id: number;
    user_id: number | null;
    is_alt: boolean;
    cp_id: number | null;
    cp_color: string | null;
    s1: number;
    s2: number;
    s3: number;
    s4: number;
    s5: number;
    s6: number;
    s7: number;
    s8: number;
    s9: number;
    adepts: number;
    dances: number;
    total_valor: number;
    total_gold: number;
    is_mine: boolean;
    is_newcomer: boolean;
    is_afk: boolean;
    afk_dates?: string;
    afk_reason?: string;
    join_date: string;
    join_days_ago: number;
    valor_tier: string;
    gold_tier: string;
    s1_details?: string[];
    s2_details?: string[];
    s3_details?: string[];
    s4_details?: string[];
    s5_details?: string[];
    s6_details?: string[];
    s7_details?: string[];
    adepts_details?: string[];
    dances_details?: string[];
    main_nickname?: string;
    parties?: { name: string; color: string }[];
}

export interface AfkHistoryItem {
    id: number;
    start: string;
    end: string;
    reason?: string;
}

export interface KHResponse {
    rows: KHTableRow[];
    start_date: string;
    end_date: string;
}

export const fetchKHTable = async (params?: Record<string, any>): Promise<KHResponse> => {
    const { data } = await api.get<KHResponse>('/dashboard/kh', { params });
    return data;
};

// --- MONEY TABLE DATA ---
export interface MoneyTableRow {
    role_id: number;
    name: string;
    class_id: number;
    total_gold: number;
    total_valor: number; // Added
    gold_count: number; // For averages
    avg_gold?: number; // Pre-calc or calc on front
    is_mine: boolean;
    is_newcomer: boolean;
    is_afk: boolean;
    join_date: string;
    join_days_ago: number;
    afk_dates?: string;
    afk_reason?: string;
    // New fields for Grouping & CP
    user_id: number | null;
    is_alt: boolean;
    cp_id: number | null;
    cp_color: string | null;
    // Interval specific
    interval_stats?: {
        label: string; // Added label 
        start: string;
        end: string;
        gold: number;
        valor: number; // Added
        is_pre_join: boolean;
        is_newcomer_stay: boolean;
        is_afk_stay: boolean;
        valor_details?: string[];
    }[];
    main_nickname?: string;
    parties?: { name: string; color: string }[];
    s1?: number;
    s2?: number;
    s3?: number;
    s4?: number;
    s5?: number;
    s6?: number;
    s7?: number;
    s8?: number;
    s9?: number;
    adepts?: number;
    dances?: number;
    s1_details?: string[];
    s2_details?: string[];
    s3_details?: string[];
    s4_details?: string[];
    s5_details?: string[];
    s6_details?: string[];
    s7_details?: string[];
    adepts_details?: string[];
    dances_details?: string[];
}

export interface MoneyResponse {
    rows: MoneyTableRow[];
    intervals: { label: string; start: string; end: string }[];
    start_date: string;
    end_date: string;
    group_period: string | null;
}

export const fetchMoneyTable = async (params?: Record<string, any>): Promise<MoneyResponse> => {
    const { data } = await api.get<MoneyResponse>('/dashboard/money', { params });
    return data;
};

// --- HISTORY DATA ---
export interface HistoryRow {
    date: string;
    name: string | null;
    class_id: number;
    class_name: string;
    desc: string;
    type: number;
    role_id: number;
    item_name: string | null;
    is_mine: boolean;
    timestamp: number;
    join_date: string;
    join_days_ago: number;
    is_afk: boolean;
    afk_dates?: string;
    afk_reason?: string;
    id: number;
}

export const fetchHistoryTable = async (params?: Record<string, any>): Promise<HistoryRow[]> => {
    const { data } = await api.get<HistoryRow[]>('/dashboard/history', { params });
    return data;
};

// --- PROFILE DATA ---
export interface ProfileLinkedChar {
    nickname: string;
    is_main: boolean;
    class_id: number;
    role_id: number;
    kh_stats?: KHStatsSummary;
}

export interface KHPeriodStats {
    s1: number;
    s2: number;
    s3: number;
    s4: number;
    s5: number;
    s6: number;
    s7: number;
    adepts: number;
    dances: number;
    total_valor: number;
}

export interface KHStatsSummary {
    day: KHPeriodStats;
    week: KHPeriodStats;
    month: KHPeriodStats;
}

export interface SquadKHCharStats {
    role_id: number;
    nickname: string;
    stats: KHPeriodStats;
}

export interface SquadKHStatsResponse {
    period: string;
    offset: number;
    start_date: string;
    end_date: string;
    squad_stats: SquadKHCharStats[];
}

export interface ProfileResponse {
    role_id: number;
    nickname: string | null;
    class_id: number;
    in_clan: boolean;
    is_alt: boolean;
    user_id: number | null;
    telegram_id: number | null;
    username: string | null;
    afk_start: string | null;
    afk_end: string | null;
    afk_reason: string | null;
    afk_history: { id: number; start: string; end: string; reason?: string }[];
    queues: { id: number; queue_id: number; name: string; auto_requeue: boolean; character_name?: string; position?: number }[];
    linked_chars: ProfileLinkedChar[];
    parties: { id: number; name: string | null; color: string | null; is_leader: boolean; members: { nickname: string; is_leader: boolean; class_id: number; role_id: number }[] }[];
    party: { id: number; name: string | null; color: string | null; is_leader: boolean; members: { nickname: string; is_leader: boolean; class_id: number; role_id: number }[] } | null;
    events: { id: number; timestamp: number; date: string; type: number; value: number; description: string | null }[];
    kh_stats?: KHStatsSummary;
    reward_history?: {
        id: number;
        character_name: string;
        queue_name: string;
        issued_by: string;
        record_type: string;
        timestamp: string;
    }[];
}

export const fetchProfile = async (roleId: number): Promise<ProfileResponse> => {
    const { data } = await api.get<ProfileResponse>(`/dashboard/profile/${roleId}`);
    return data;
};

export const updateProfile = async (roleId: number, data: any): Promise<any> => {
    const response = await api.post(`/dashboard/profile/${roleId}`, data);
    return response.data;
};

export const fetchSquadKHStats = async (roleId: number, period: string, offset: number): Promise<SquadKHStatsResponse> => {
    const { data } = await api.get<SquadKHStatsResponse>(`/dashboard/profile/${roleId}/squad_kh_stats`, {
        params: { period, offset }
    });
    return data;
};

export const updateCharacterNickname = async (roleId: number, charRoleId: number, nickname: string): Promise<void> => {
    const response = await api.patch(`/dashboard/profile/${roleId}/linked_chars/${charRoleId}/nickname`, { nickname });
    return response.data;
};

export const updatePartyName = async (partyId: number, name: string): Promise<any> => {
    const response = await api.post('/party/rename', { party_id: partyId, name });
    return response.data;
};

export const updatePartyColor = async (partyId: number, color: string): Promise<any> => {
    const response = await api.post('/party/color', { party_id: partyId, color });
    return response.data;
};

export const addEvent = async (data: { role_id: number, date: string, value: number, description?: string }): Promise<any> => {
    const response = await api.post('/add_event', data);
    return response.data;
};

export const addEventBulk = async (data: { role_ids: number[], date: string, value: number, description?: string }): Promise<any> => {
    const response = await api.post('/add_event_bulk', data);
    return response.data;
};

export const deleteEvent = async (eventId: number): Promise<any> => {
    const response = await api.post('/delete_event', { event_id: eventId });
    return response.data;
};

export const addAfkHistory = async (data: { user_id?: number, role_id?: number, start: string, end?: string | null, reason?: string }): Promise<any> => {
    const response = await api.post('/afk/add', data);
    return response.data;
};

export const joinQueue = async (data: { user_id: number, queue_id: number, character_name: string, auto_requeue?: boolean }): Promise<any> => {
    const response = await api.post('/queue/join', data);
    return response.data;
};

export const leaveQueue = async (entryId: number): Promise<any> => {
    const response = await api.post('/queue/leave', { entry_id: entryId });
    return response.data;
};

export const updateQueueEntry = async (entryId: number, characterName: string, autoRequeue: boolean): Promise<any> => {
    const response = await api.post('/queue/update_entry', { entry_id: entryId, character_name: characterName, auto_requeue: autoRequeue });
    return response.data;
};

export const fetchQueueEntries = async (queueId: number): Promise<any> => {
    const response = await api.post('/master/queue_entries', { queue_id: queueId });
    return response.data;
};

export const linkCharacter = async (userId: number, nickname: string): Promise<any> => {
    const response = await api.post('/character/link', { user_id: userId, nickname });
    return response.data;
};

export const unlinkCharacter = async (roleId: number, nickname?: string): Promise<any> => {
    const response = await api.post('/character/unlink', { role_id: roleId, nickname });
    return response.data;
};


export const deleteAfkHistory = async (afkId: number): Promise<any> => {
    const response = await api.post('/afk/delete', { afk_id: afkId });
    return response.data;
};

export const kickPartyMember = async (partyId: number, memberRoleId: number): Promise<any> => {
    const { data } = await api.post('/dashboard/party/kick', { party_id: partyId, role_id: memberRoleId });
    if (data.status === 'error') throw new Error(data.message || "Error");
    return { status: 'ok' };
};

export const transferPartyLeadership = async (partyId: number, newLeaderRoleId: number): Promise<any> => {
    const { data } = await api.post('/dashboard/party/transfer_leadership', { party_id: partyId, new_leader_role_id: newLeaderRoleId });
    if (data.status === 'error') throw new Error(data.message || "Error");
    return { status: 'ok' };
};

// --- OBSERVER ---
export const fetchObserver = async (roleId: number): Promise<{ status: string; html: string; message?: string }> => {
    const response = await api.get<{ status: string; html: string; message?: string }>(`/observer/${roleId}`);
    return response.data;
};

export const logout = async (): Promise<any> => {
    const response = await api.post('/logout');
    return response.data;
};

// --- MASTER PANEL (New) ---

export interface MasterUser {
    id: number;
    telegram_id: number;
    username: string | null;
    main_nickname: string | null;
    main_role_id: number | null;
    characters: {
        nickname: string;
        is_main: boolean;
        is_in_clan: boolean;
    }[];
    is_master: boolean;
    is_banned: boolean;
    is_in_clan: boolean;
    is_phantom: boolean;
    afk_start: string | null;
    afk_end: string | null;
}

export interface MasterUsersResponse {
    users: MasterUser[];
    total_users: number;
    active_clan_users: number;
    total_chars: number;
    chars_in_clan: number;
    total_clan_players: number;
}

export const fetchMasterUsers = async (): Promise<MasterUsersResponse> => {
    const { data } = await api.get('/master/users');
    if (data.status === 'error') throw new Error(data.message);
    return {
        users: data.users,
        total_users: data.total_users,
        active_clan_users: data.active_clan_users,
        total_chars: data.total_chars,
        chars_in_clan: data.chars_in_clan,
        total_clan_players: data.total_clan_players
    };
};

export const toggleUserBan = async (userId: number): Promise<boolean> => {
    const { data } = await api.post('/master/user/toggle_ban', { user_id: userId });
    if (data.status === 'error') throw new Error(data.message);
    return data.is_banned;
};

export const toggleUserMaster = async (userId: number): Promise<boolean> => {
    const { data } = await api.post('/master/user/toggle_master', { user_id: userId });
    if (data.status === 'error') throw new Error(data.message);
    return data.is_master;
};

export const deleteUser = async (userId: number): Promise<void> => {
    const { data } = await api.post('/master/user/delete', { user_id: userId });
    if (data.status === 'error') throw new Error(data.message);
};

export const fetchVerificationCode = async (): Promise<string> => {
    const { data } = await api.get('/master/settings/verification_code');
    if (data.status === 'error') throw new Error(data.message);
    return data.code;
};

export const updateVerificationCode = async (code: string): Promise<void> => {
    const { data } = await api.post('/master/settings/verification_code', { code });
    if (data.status === 'error') throw new Error(data.message);
};

export const fetchMasterAfk = async (): Promise<any[]> => {
    const { data } = await api.get('/master/afk');
    if (data.status === 'error') throw new Error(data.message);
    return data.afk_players;
};

export const saveMasterAfk = async (userId: number, start: string, end: string, reason: string): Promise<void> => {
    const { data } = await api.post('/master/afk/save', { user_id: userId, start, end, reason });
    if (data.status === 'error') throw new Error(data.message);
};

export const deleteMasterAfk = async (userId: number): Promise<void> => {
    const { data } = await api.post('/master/afk/delete', { user_id: userId });
    if (data.status === 'error') throw new Error(data.message);
};

export const fetchMasterAfkHistory = async (): Promise<any[]> => {
    const { data } = await api.get('/master/afk/history');
    if (data.status === 'error') throw new Error(data.message);
    return data.history;
};

export const sendAnnouncement = async (payload: { text: string; schedule_type: string; run_time?: string; days_of_week?: string }): Promise<string> => {
    const { data } = await api.post('/master/announce', payload);
    if (data.status === 'error') throw new Error(data.message);
    return data.message || 'Объявление отправлено';
};

// --- ADMIN SETTINGS & BACKUPS ---

export const fetchAdminSettings = async (): Promise<AdminSettings> => {
    const { data } = await api.get<AdminSettings>('/dashboard/admin/settings');
    return data;
};

export const updateAdminSettings = async (settings: AdminSettings): Promise<void> => {
    await api.post('/dashboard/admin/settings', settings);
};

export const fetchBackups = async (): Promise<BackupFile[]> => {
    const { data } = await api.get<BackupFile[]>('/dashboard/admin/backups');
    return data;
};

export const createBackup = async (): Promise<void> => {
    await api.post('/dashboard/admin/backups/create');
};

export const deleteBackup = async (filename: string): Promise<void> => {
    await api.delete(`/dashboard/admin/backups/${filename}`);
};

export const restoreBackup = async (filename: string): Promise<void> => {
    await api.post(`/dashboard/admin/backups/restore/${filename}`);
};

// --- CP (Constant Party) Management ---

export interface CPListItem {
    id: number;
    name: string | null;
    leader_nickname: string | null;
    member_count: number;
}

export interface CPApplicationItem {
    application_id: number;
    applicant_role_id: number;
    applicant_nickname: string | null;
    applicant_class_id: number;
    created_at: string;
}

export const setMainCharacter = async (roleId: number, newMainRoleId: number): Promise<void> => {
    const { data } = await api.post(`/dashboard/profile/${roleId}/set_main`, { new_main_role_id: newMainRoleId });
    if (data.status === 'error') throw new Error(data.message || "Error");
};

export const fetchAllParties = async (): Promise<CPListItem[]> => {
    const { data } = await api.get('/dashboard/party/list');
    return data.parties;
};

export const applyToParty = async (partyId: number): Promise<void> => {
    const { data } = await api.post('/dashboard/party/apply', { party_id: partyId });
    if (data.status === 'error') throw new Error(data.message || "Error");
};

export const fetchPartyApplications = async (partyId: number): Promise<CPApplicationItem[]> => {
    const { data } = await api.get(`/dashboard/party/${partyId}/applications`);
    return data.applications;
};

export const resolvePartyApplication = async (applicationId: number, action: 'accept' | 'reject'): Promise<void> => {
    const { data } = await api.post('/dashboard/party/applications/resolve', { application_id: applicationId, action });
    if (data.status === 'error') throw new Error(data.message || "Error");
};

export const createNamedParty = async (name?: string): Promise<number> => {
    const { data } = await api.post('/dashboard/party/create_named', { name });
    if (data.status === 'error') throw new Error(data.message || "Error");
    return data.party_id;
};

export const addCPMember = async (partyId: number, nickname: string): Promise<void> => {
    const { data } = await api.post('/dashboard/party/add_member', { party_id: partyId, nickname });
    if (data.status === 'error') throw new Error(data.message || "Error");
};

export const fetchPartyKHStats = async (roleId: number, period: string, offset: number): Promise<SquadKHStatsResponse> => {
    const { data } = await api.get<SquadKHStatsResponse>(`/dashboard/party/${roleId}/kh_stats`, {
        params: { period, offset }
    });
    return data;
};




export default api;
