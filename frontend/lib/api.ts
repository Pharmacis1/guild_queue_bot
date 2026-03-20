import axios from 'axios';

const api = axios.create({
    baseURL: '/api', // Proxied to backend via next.config.mjs
    withCredentials: true, // Important for session cookies (Auth)
});

// --- INIT DATA ---
export interface InitData {
    user: UserData | null;
    classes: Record<string, [string, string, string]>;
    queue_types: { id: number; name: string }[];
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
}

export const fetchInitData = async (): Promise<InitData> => {
    const { data } = await api.get<InitData>('/dashboard/init');
    return data;
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
    queues: { id: number; name: string; auto_requeue: boolean; character_name?: string }[];
    linked_chars: { nickname: string; is_main: boolean; class_id?: number }[];
    parties: { id: number; name: string | null; color: string | null; is_leader: boolean; members: { nickname: string; is_leader: boolean; class_id: number; role_id: number }[] }[];
    party: { id: number; name: string | null; color: string | null; is_leader: boolean; members: { nickname: string; is_leader: boolean; class_id: number; role_id: number }[] } | null;
    events: { timestamp: number; date: string; type: number; value: number; description: string | null }[];
}

export const fetchProfile = async (roleId: number): Promise<ProfileResponse> => {
    const { data } = await api.get<ProfileResponse>(`/dashboard/profile/${roleId}`);
    return data;
};

export const updateProfile = async (roleId: number, data: any): Promise<any> => {
    const response = await api.post(`/dashboard/profile/${roleId}`, data);
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

export const addAfkHistory = async (data: { user_id?: number, role_id?: number, start: string, end: string, reason?: string }): Promise<any> => {
    const response = await api.post('/afk/add', data);
    return response.data;
};


export const deleteAfkHistory = async (afkId: number): Promise<any> => {
    const response = await api.post('/afk/delete', { afk_id: afkId });
    return response.data;
};

export const transferPartyLeadership = async (partyId: number, newLeaderRoleId: number): Promise<any> => {
    const response = await api.post('/party/transfer_leadership', { party_id: partyId, new_leader_role_id: newLeaderRoleId });
    return response.data;
};

export const kickPartyMember = async (memberRoleId: number): Promise<any> => {
    const response = await api.post('/party/kick', { member_role_id: memberRoleId });
    return response.data;
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

export default api;
