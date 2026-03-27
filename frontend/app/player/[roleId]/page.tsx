'use client';

import React, { useEffect, useState, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { 
    fetchProfile, 
    ProfileResponse, 
    joinQueue, 
    leaveQueue, 
    fetchInitData,
    InitData,
    fetchSquadKHStats,
    SquadKHStatsResponse,
    CPListItem,
    CPApplicationItem,
    fetchAllParties,
    applyToParty,
    fetchPartyApplications,
    resolvePartyApplication,
    createNamedParty,
    fetchPartyKHStats,
    loginViaTMA,
    addCPMember,
    kickPartyMember,
    transferPartyLeadership,
    updateQueueEntry,
    fetchQueueEntries
} from '@/lib/api';
import ClassIcon from '@/app/components/shared/ClassIcon';
import SettingsModal from '@/app/components/modals/SettingsModal';
import styles from './ProfileLite.module.css';

export default function PlayerProfileLite() {
    const params = useParams();
    const router = useRouter();
    const roleId = params.roleId ? parseInt(params.roleId as string) : null;
    
    // Core Data
    const [profile, setProfile] = useState<ProfileResponse | null>(null);
    const [initData, setInitData] = useState<InitData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // UI State
    const [activeTab, setActiveTab] = useState<'kh' | 'queues' | 'cp'>('kh');
    const [selectedPeriod, setSelectedPeriod] = useState<'day' | 'week' | 'month'>('week');
    const [khOffset, setKhOffset] = useState(0);
    const [squadStats, setSquadStats] = useState<SquadKHStatsResponse | null>(null);

    // Modal States
    const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);
    const [modalMode, setModalMode] = useState<'settings' | 'afk'>('settings');
    const [isQueueFormOpen, setIsQueueFormOpen] = useState(false);
    const [isQueueParticipantsOpen, setIsQueueParticipantsOpen] = useState(false);
    
    // Queue Form Data
    const [queueForm, setQueueForm] = useState<{ queue_id: number, character_name: string, auto_requeue: boolean, entry_id?: number } | null>(null);
    const [queueParticipants, setQueueParticipants] = useState<any[]>([]);
    const [selectedQueueId, setSelectedQueueId] = useState<number | null>(null);
    
    // CP State
    const [cpList, setCpList] = useState<CPListItem[]>([]);
    const [cpApplications, setCpApplications] = useState<CPApplicationItem[]>([]);
    const [cpStats, setCpStats] = useState<SquadKHStatsResponse | null>(null);
    const [isCreatingCP, setIsCreatingCP] = useState(false);
    const [newCpName, setNewCpName] = useState('');
    const [addMemberNick, setAddMemberNick] = useState('');
    const [isAddingMember, setIsAddingMember] = useState<number | null>(null);

    const isTMA = typeof window !== 'undefined' && !!(window as any).Telegram?.WebApp?.initData;

    const isMyProfile = useMemo(() => {
        if (!profile) return false;
        if (initData?.user) {
            const profileUserId = profile.user_id ? Number(profile.user_id) : null;
            const currentUserId = initData.user.id ? Number(initData.user.id) : null;
            if (profileUserId !== null && currentUserId !== null && profileUserId === currentUserId) return true;

            const profileTgId = profile.telegram_id ? Number(profile.telegram_id) : null;
            const currentTgId = initData.user.telegram_id ? Number(initData.user.telegram_id) : null;
            if (profileTgId !== null && currentTgId !== null && profileTgId === currentTgId) return true;
        }
        return false;
    }, [profile, initData]);

    const isMaster = useMemo(() => initData?.user?.is_master || false, [initData]);
    const canEdit = isMaster || isMyProfile || (isTMA && !profile?.user_id);

    const loadAll = async () => {
        if (!roleId) return;
        try {
            setLoading(true);
            let init = await fetchInitData();
            if (!init.user && isTMA) {
                try {
                    await loginViaTMA((window as any).Telegram.WebApp.initData);
                    init = await fetchInitData();
                } catch (e) {}
            }
            const profileData = await fetchProfile(roleId);
            setProfile(profileData);
            setInitData(init);
            setError(null);
        } catch (err: any) {
            console.error('Failed to load profile:', err);
            setError('Ошибка загрузки данных профиля.');
        } finally {
            setLoading(false);
        }
    };

    // Tabs will be switched manually for now to avoid Suspense layout issues
    // useEffect(() => { ... }) removed


    useEffect(() => { loadAll(); }, [roleId]);

    useEffect(() => {
        if (!roleId) return;
        fetchSquadKHStats(roleId, selectedPeriod, khOffset)
            .then(setSquadStats)
            .catch(console.error);
    }, [roleId, selectedPeriod, khOffset]);

    useEffect(() => {
        if (activeTab === 'cp') {
            if (profile?.parties && profile.parties.length > 0) {
                // Fetch stats for the first party if available, or just fetch for roleId which returns party stats if in one
                fetchPartyKHStats(roleId!, selectedPeriod, khOffset).then(setCpStats).catch(console.error);
                
                const leaderParty = profile.parties.find(p => p.is_leader);
                if (leaderParty) {
                    fetchPartyApplications(leaderParty.id).then(setCpApplications).catch(console.error);
                }
            } else {
                fetchAllParties().then(setCpList).catch(console.error);
            }
        }
    }, [activeTab, profile?.parties, roleId, selectedPeriod, khOffset]);

    const handleJoinQueue = async () => {
        if (!profile || !queueForm) return;
        try {
            await joinQueue({
                user_id: profile.user_id!,
                queue_id: queueForm.queue_id,
                character_name: queueForm.character_name,
                auto_requeue: queueForm.auto_requeue
            });
            setIsQueueFormOpen(false);
            loadAll();
        } catch (err: any) {
            alert(err.response?.data?.message || 'Ошибка вступления');
        }
    };

    const handleLeaveQueue = async (entryId: number) => {
        if (!confirm('Выйти из очереди?')) return;
        try {
            await leaveQueue(entryId);
            loadAll();
        } catch (e) { alert('Ошибка выхода'); }
    };

    const handleUpdateQueueEntry = async () => {
        if (!queueForm?.entry_id) return;
        try {
            await updateQueueEntry(queueForm.entry_id, queueForm.character_name, queueForm.auto_requeue);
            setIsQueueFormOpen(false);
            loadAll();
        } catch (e) { alert('Ошибка обновления'); }
    };

    const handleShowParticipants = async (qId: number) => {
        try {
            const data = await fetchQueueEntries(qId);
            setQueueParticipants(data.entries || []);
            setSelectedQueueId(qId);
            setIsQueueParticipantsOpen(true);
        } catch (err) { alert('Ошибка загрузки'); }
    };

    const handleCreateCP = async () => {
        try {
            await createNamedParty(newCpName);
            setIsCreatingCP(false);
            setNewCpName('');
            loadAll();
        } catch (e) { alert('Ошибка создания'); }
    };

    const handleAddMember = async (partyId: number) => {
        if (!addMemberNick) return;
        try {
            await addCPMember(partyId, addMemberNick);
            setAddMemberNick('');
            setIsAddingMember(null);
            loadAll();
        } catch (e) { alert('Ошибка добавления'); }
    };

    const handleKickMember = async (partyId: number, rId: number, nick: string) => {
        if (!confirm(`Исключить ${nick}?`)) return;
        try {
            await kickPartyMember(partyId, rId);
            loadAll();
        } catch (e) { alert('Ошибка исключения'); }
    };

    const handleTransferLeadership = async (partyId: number, rId: number) => {
        if (!confirm('Передать лидерку?')) return;
        try {
            await transferPartyLeadership(partyId, rId);
            loadAll();
        } catch (e) { alert('Ошибка передачи'); }
    };

    const handlePeriodChange = (p: 'day' | 'week' | 'month') => {
        setSelectedPeriod(p);
        setKhOffset(0);
    };

    const getPaginatorLabel = () => {
        if (!squadStats) return "...";
        const fmt = (s: string) => new Date(s).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
        if (selectedPeriod === 'day') return fmt(squadStats.start_date);
        return `${fmt(squadStats.start_date)} - ${fmt(squadStats.end_date)}`;
    };

    if (loading) return <div className={styles.container}><div className={styles.loadingSpinner}></div></div>;
    if (error || !profile) return <div className={styles.container}><div className={styles.card}>{error || 'Игрок не найден'}</div></div>;

    return (
        <div className={styles.tmaMode}>
            <div className={styles.container}>
                <div className={styles.header}>
                    <ClassIcon classId={profile.class_id} size={42} />
                    <div style={{ flex: 1, marginLeft: '12px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <h1 className={styles.nickname}>{profile.nickname}</h1>
                            {profile.afk_start && profile.afk_end && (
                                <div className={styles.afkBadgeHeader} title={`Отсутствует до ${profile.afk_end}`}>
                                    ☕ AFK
                                </div>
                            )}
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <div className={styles.roleId}>ID: {profile.role_id}</div>
                            <div className={`${styles.badge} ${profile.is_alt ? styles.badgeAlt : styles.badgeMain}`}>
                                {profile.is_alt ? 'ТВИН' : 'ОСНОВА'}
                            </div>
                        </div>
                    </div>
                </div>

                {canEdit && (
                    <div className={styles.actionBar}>
                        <button 
                            className={styles.btnAfkWide} 
                            onClick={() => { setModalMode('afk'); setIsSettingsModalOpen(true); }}
                        >
                            ☕ Сообщить об отсутствии
                        </button>
                        <button 
                            className={styles.btnSettingsCircle} 
                            onClick={() => { setModalMode('settings'); setIsSettingsModalOpen(true); }}
                        >
                            ⚙️
                        </button>
                    </div>
                )}

                <div className={styles.mainTabs}>
                    <button id="tab-kh" className={`${styles.mainTabBtn} ${activeTab === 'kh' ? styles.mainTabActive : ''}`} onClick={() => setActiveTab('kh')}>КХ</button>
                    <button id="tab-queues" className={`${styles.mainTabBtn} ${activeTab === 'queues' ? styles.mainTabActive : ''}`} onClick={() => setActiveTab('queues')}>Очереди</button>
                    <button id="tab-cp" className={`${styles.mainTabBtn} ${activeTab === 'cp' ? styles.mainTabActive : ''}`} onClick={() => setActiveTab('cp')}>КП</button>
                </div>

                {activeTab === 'kh' && (
                    <div className={styles.card}>
                        <div className={styles.statsTabs}>
                            {(['day', 'week', 'month'] as const).map(p => (
                                <button key={p} className={`${styles.tabBtn} ${selectedPeriod === p ? styles.tabBtnActive : ''}`} onClick={() => handlePeriodChange(p)}>
                                    {p === 'day' ? 'День' : p === 'week' ? 'Неделя' : 'Месяц'}
                                </button>
                            ))}
                        </div>
                        <div className={styles.paginator}>
                            <button className={styles.pageBtn} onClick={() => setKhOffset(o => o - 1)}>&lt;</button>
                            <span>{getPaginatorLabel()}</span>
                            <button className={styles.pageBtn} onClick={() => setKhOffset(o => o + 1)} disabled={khOffset >= 0}>&gt;</button>
                        </div>
                        <div className={styles.squadTable}>
                            {squadStats?.squad_stats?.map((char, i) => (
                                <div key={i} className={`${styles.squadRow} ${char.role_id === roleId ? styles.squadRowActive : ''}`} onClick={() => router.push(`/player/${char.role_id}`)}>
                                    <ClassIcon classId={profile?.linked_chars?.find(c => c.role_id === char.role_id)?.class_id || 0} size={24} />
                                    <span className={styles.squadNick} style={{flex: 1, marginLeft: '8px'}}>{char.nickname}</span>
                                    
                                    <div className={styles.squadStages}>
                                        {[1, 2, 3, 4, 5, 6, 7].map(num => {
                                            const val = (char.stats as any)[`s${num}`];
                                            return (
                                                <div key={num} className={`${styles.stageBox} ${val > 0 ? styles.stageBoxActive : ''}`}>
                                                    {num}
                                                    {val > 1 && <span className={styles.stageBadge}>x{val}</span>}
                                                </div>
                                            );
                                        })}
                                    </div>

                                    <span className={styles.squadTotalKH}>{char.stats.total_valor}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {activeTab === 'queues' && (
                    <div className={styles.card} style={{ textAlign: 'center', padding: '40px 20px', color: '#666' }}>
                        <div style={{ fontSize: '2rem', marginBottom: '10px' }}>📋</div>
                        <div style={{ fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '1px' }}>Очереди в разработке</div>
                        <div style={{ fontSize: '0.8rem', marginTop: '10px' }}>Система записи в очереди скоро будет доступна</div>
                    </div>
                )}

                {activeTab === 'cp' && (
                    <div className={styles.card} style={{ textAlign: 'center', padding: '40px 20px', color: '#666' }}>
                        <div style={{ fontSize: '2rem', marginBottom: '10px' }}>⚔️</div>
                        <div style={{ fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '1px' }}>Раздел КП в разработке</div>
                        <div style={{ fontSize: '0.8rem', marginTop: '10px' }}>Управление конст-пати появится в ближайшее время</div>
                    </div>
                )}
            </div>

            {isSettingsModalOpen && (
                <SettingsModal 
                    key={modalMode}
                    data={initData} 
                    onClose={() => setIsSettingsModalOpen(false)} 
                    onRefresh={loadAll} 
                    initialShowAfk={modalMode === 'afk'} 
                />
            )}

            {isQueueFormOpen && queueForm && (
                <div className={styles.modalOverlay}>
                    <div className={styles.modalContent} style={{background: '#111', padding: '20px', borderRadius: '16px'}}>
                        <h3 style={{color:'#fff', marginBottom: '16px'}}>Запись в очередь</h3>
                        <input className={styles.input} value={queueForm.character_name} onChange={e => setQueueForm({...queueForm, character_name: e.target.value})} placeholder="Никнейм" />
                        <label style={{display:'flex', alignItems:'center', gap:'8px', marginTop:'12px', color:'#ccc'}}>
                            <input type="checkbox" checked={queueForm.auto_requeue} onChange={e => setQueueForm({...queueForm, auto_requeue: e.target.checked})} />
                            Авто-перезапись
                        </label>
                        <div style={{display:'flex', gap:'8px', marginTop:'20px'}}>
                            <button className={styles.btnAction} onClick={queueForm.entry_id ? handleUpdateQueueEntry : handleJoinQueue}>ОК</button>
                            <button className={`${styles.btnAction} ${styles.btnSecondary}`} onClick={() => setIsQueueFormOpen(false)}>Отмена</button>
                        </div>
                    </div>
                </div>
            )}

            {isQueueParticipantsOpen && (
                <div className={styles.modalOverlay}>
                    <div className={styles.modalContent} style={{background: '#111', padding: '20px', borderRadius: '16px', maxHeight: '80vh', overflowY: 'auto'}}>
                        <h3 style={{color:'#fff', marginBottom: '16px'}}>Участники</h3>
                        <div style={{display:'flex', flexDirection:'column', gap:'8px'}}>
                            {queueParticipants.map((p, i) => (
                                <div key={i} style={{padding:'8px', background:'rgba(255,255,255,0.05)', borderRadius:'8px', display:'flex', justifyContent:'space-between'}}>
                                    <span style={{color: p.is_mine ? '#ffd700' : '#fff'}}>{p.character_name}</span>
                                    <span style={{color: '#666'}}>#{p.position}</span>
                                </div>
                            ))}
                        </div>
                        <button className={styles.btnAction} onClick={() => setIsQueueParticipantsOpen(false)} style={{marginTop:'20px'}}>Закрыть</button>
                    </div>
                </div>
            )}
        </div>
    );
}
