'use client';

import React, { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { fetchProfile, ProfileResponse } from '@/lib/api';
import ClassIcon from '@/app/components/shared/ClassIcon';
import styles from './ProfileLite.module.css';

export default function PlayerProfileLite() {
    const params = useParams();
    const roleId = params.roleId ? parseInt(params.roleId as string) : null;
    
    const [profile, setProfile] = useState<ProfileResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        // Initialize Telegram WebApp
        if (typeof window !== 'undefined' && (window as any).Telegram?.WebApp) {
            const tg = (window as any).Telegram.WebApp;
            tg.ready();
            tg.expand();
            // Set header color to match our theme
            tg.setHeaderColor('#080808');
        }
    }, []);

    useEffect(() => {
        if (!roleId) return;

        const loadProfile = async () => {
            try {
                setLoading(true);
                const data = await fetchProfile(roleId);
                setProfile(data);
                setError(null);
            } catch (err: any) {
                console.error('Failed to fetch profile:', err);
                setError('Игрок не найден или ошибка сервера');
            } finally {
                setLoading(false);
            }
        };

        loadProfile();
    }, [roleId]);

    if (loading) {
        return <div className={styles.loading}>Загрузка профиля...</div>;
    }

    if (error || !profile) {
        return <div className={styles.error}>{error || 'Профиль не найден'}</div>;
    }

    return (
        <div className={styles.tmaMode}>
            <div className={styles.container}>
                {/* Header Section */}
                <div className={styles.header}>
                    <div className={styles.avatarOuter}>
                        <ClassIcon classId={profile.class_id} size={40} />
                    </div>
                    <div>
                        <h1 className={styles.nickname}>{profile.nickname}</h1>
                        <div className={styles.roleId}>ID: {profile.role_id}</div>
                    </div>
                </div>

                {/* Status Card */}
                <div className={styles.card}>
                    <div className={styles.sectionTitle}>Статус</div>
                    <div className={styles.infoItem}>
                        <span className={styles.infoLabel}>В клане</span>
                        <span className={`${styles.infoValue} ${profile.in_clan ? styles.statusOn : styles.statusOff}`}>
                            {profile.in_clan ? 'Да' : 'Нет'}
                        </span>
                    </div>
                    {profile.afk_start && (
                        <div className={styles.infoItem}>
                            <span className={styles.infoLabel}>АФК до</span>
                            <span className={styles.infoValue}>{profile.afk_end || 'Неизвестно'}</span>
                        </div>
                    )}
                </div>

                {/* Characters Card */}
                {profile.linked_chars && profile.linked_chars.length > 0 && (
                    <div className={styles.card}>
                        <div className={styles.sectionTitle}>Персонажи</div>
                        {profile.linked_chars.map((char, idx) => (
                            <div key={idx} className={styles.infoItem}>
                                <span className={styles.infoLabel}>{char.nickname}</span>
                                <span className={styles.infoValue}>{char.is_main ? 'Мейн' : 'Твин'}</span>
                            </div>
                        ))}
                    </div>
                )}

                {/* Recent Events Card */}
                {profile.events && profile.events.length > 0 && (
                    <div className={styles.card}>
                        <div className={styles.sectionTitle}>Последние события</div>
                        <ul className={styles.historyList}>
                            {profile.events.slice(0, 10).map((event) => (
                                <li key={event.id} className={styles.historyItem}>
                                    <span className={styles.historyValue}>
                                        {event.value > 0 ? `+${event.value}` : event.value}
                                    </span>
                                    <div className={styles.historyDate}>{event.date}</div>
                                    <div className={styles.historyDesc}>{event.description || 'Начисление'}</div>
                                </li>
                            ))}
                        </ul>
                    </div>
                )}
                
                {/* Script for Telegram SDK */}
                <script src="https://telegram.org/js/telegram-web-app.js" async />
            </div>
        </div>
    );
}
