import axios from 'axios';

const api = axios.create({
    baseURL: '/api', // Proxied to backend via next.config.mjs
    withCredentials: true, // Important for session cookies (Auth)
});

// --- INIT DATA ---
export interface InitData {
    user: UserData | null;
    classes: Record<string, [string, string, string]>;
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
    total_gold: number;
    is_mine: boolean;
    is_newcomer: boolean;
    is_afk: boolean;
    afk_dates?: string;
    join_date: string;
    join_days_ago: number;
    valor_tier: string;
    gold_tier: string;
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
    gold_count: number; // For averages
    avg_gold?: number; // Pre-calc or calc on front
    is_mine: boolean;
    is_newcomer: boolean;
    is_afk: boolean;
    join_date: string;
    join_days_ago: number;
    // Interval specific
    interval_stats?: {
        start: string;
        end: string;
        gold: number;
        is_pre_join: boolean;
        is_newcomer_stay: boolean;
        is_afk_stay: boolean;
    }[];
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
    afk_history: { start: string; end: string }[];
    queues: { id: number; name: string; auto_requeue: boolean }[];
    linked_chars: { nickname: string; is_main: boolean }[];
    party: { id: number; name: string | null; is_leader: boolean; members: any[] } | null;
}

export const fetchProfile = async (roleId: number): Promise<ProfileResponse> => {
    const { data } = await api.get<ProfileResponse>(`/dashboard/profile/${roleId}`);
    return data;
};

export const updateProfile = async (roleId: number, data: any): Promise<any> => {
    const response = await api.post(`/dashboard/profile/${roleId}`, data);
    return response.data;
};

export default api;
