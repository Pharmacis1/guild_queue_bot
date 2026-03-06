import React, { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';

interface PlayerTooltipProps {
    joinDate: string;
    joinDaysAgo: number;
    afkDates?: string;
    isAfk: boolean;
    afkReason?: string;
    mainNickname?: string;
    parties?: { name: string; color: string }[];
    children: React.ReactNode;
}

const PlayerTooltip: React.FC<PlayerTooltipProps> = ({
    joinDate,
    joinDaysAgo,
    afkDates,
    isAfk,
    afkReason,
    mainNickname,
    parties,
    children
}) => {
    const triggerRef = useRef<HTMLDivElement>(null);
    const [isVisible, setIsVisible] = useState(false);
    const [coords, setCoords] = useState({ top: 0, left: 0 });

    // Don't show tooltip if no data
    if (!joinDate && !isAfk && !mainNickname && (!parties || parties.length === 0)) {
        return <>{children}</>;
    }

    const onMouseEnter = () => {
        if (triggerRef.current) {
            const rect = triggerRef.current.getBoundingClientRect();
            setCoords({
                top: rect.top + window.scrollY - 10,
                left: rect.left + window.scrollX + (rect.width / 2)
            });
            setIsVisible(true);
        }
    };

    return (
        <>
            <div
                ref={triggerRef}
                className="player-tooltip-wrapper"
                style={{ position: 'relative', display: 'inline-block', cursor: 'pointer' }}
                onMouseEnter={onMouseEnter}
                onMouseLeave={() => setIsVisible(false)}
            >
                {children}
            </div>

            {isVisible && createPortal(
                <div
                    className="player-tooltip-content"
                    style={{
                        position: 'absolute',
                        top: coords.top,
                        left: coords.left,
                        transform: 'translate(-50%, -100%)',
                        marginBottom: '10px',
                        background: 'rgba(10, 10, 10, 0.98)',
                        border: '1px solid rgba(255, 255, 255, 0.15)',
                        borderRadius: '8px',
                        padding: '12px 16px',
                        zIndex: 99999,
                        width: 'max-content',
                        maxWidth: '320px',
                        minWidth: '220px',
                        whiteSpace: 'normal',
                        wordWrap: 'break-word',
                        boxShadow: '0 10px 30px rgba(0,0,0,0.9)',
                        pointerEvents: 'none',
                        animation: 'fadeIn 0.2s ease-out',
                        color: '#eee',
                        fontFamily: 'Montserrat, sans-serif'
                    }}
                >
                    {/* Character Context */}
                    {mainNickname && (
                        <div style={{ marginBottom: '8px', borderBottom: '1px solid rgba(255, 255, 255, 0.05)', paddingBottom: '6px' }}>
                            <div style={{ fontSize: '0.7rem', color: '#666', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Основа</div>
                            <div style={{ fontSize: '0.9rem', color: '#fff', fontWeight: 600 }}>{mainNickname}</div>
                        </div>
                    )}

                    {/* Parties */}
                    {parties && parties.length > 0 && (
                        <div style={{ marginBottom: '8px', borderBottom: '1px solid rgba(255, 255, 255, 0.05)', paddingBottom: '6px' }}>
                            <div style={{ fontSize: '0.7rem', color: '#666', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Состоит в КП</div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '4px' }}>
                                {parties.map((p, idx) => (
                                    <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                        <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: p.color || '#fff', boxShadow: `0 0 5px ${p.color} ` }}></div>
                                        <div style={{ fontSize: '0.85rem', color: '#ccc' }}>{p.name}</div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* AFK Status and Reason */}
                    {isAfk && (
                        <div style={{ marginBottom: '8px', borderBottom: '1px solid rgba(255, 255, 255, 0.05)', paddingBottom: '6px' }}>
                            <div style={{ fontSize: '0.7rem', color: '#666', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Статус</div>
                            <div style={{ fontSize: '0.9rem', color: 'var(--accent-ruby)', fontWeight: 600 }}>
                                ⛔ AFK
                                {afkReason && <span style={{ marginLeft: '6px', fontSize: '0.8rem', color: '#ccc' }}>({afkReason})</span>}
                            </div>
                        </div>
                    )}

                    {/* Dates */}
                    <div style={{ marginBottom: isAfk ? '8px' : '0' }}>
                        <div style={{ fontSize: '0.7rem', color: '#666', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Дата вступления</div>
                        <div style={{ fontSize: '0.9rem', color: '#ccc', fontWeight: 600 }}>
                            {joinDate || 'Неизвестно'}
                            {joinDaysAgo > 0 && <span style={{ color: 'var(--accent-ruby)', marginLeft: '6px', fontSize: '0.75rem' }}>({joinDaysAgo} дн. назад)</span>}
                        </div>
                    </div>

                    {isAfk && afkDates && (
                        <div style={{ borderTop: '1px solid rgba(255, 255, 255, 0.05)', paddingTop: '6px' }}>
                            <div style={{ fontSize: '0.7rem', color: '#666', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Период АФК</div>
                            <div style={{ fontSize: '0.9rem', color: 'var(--accent-ruby)', fontWeight: 600 }}>{afkDates}</div>
                        </div>
                    )}

                    {/* Arrow */}
                    <div style={{
                        position: 'absolute',
                        top: '100%',
                        left: '50%',
                        transform: 'translateX(-50%)',
                        width: 0,
                        height: 0,
                        borderLeft: '6px solid transparent',
                        borderRight: '6px solid transparent',
                        borderTop: '6px solid rgba(255, 255, 255, 0.15)'
                    }} />

                    <style jsx>{`
                        @keyframes fadeIn {
                            from { opacity: 0; transform: translate(-50%, -90%); }
                            to { opacity: 1; transform: translate(-50%, -100%); }
                        }
                    `}</style>
                </div>,
                document.body
            )}
        </>
    );
};

export default PlayerTooltip;
