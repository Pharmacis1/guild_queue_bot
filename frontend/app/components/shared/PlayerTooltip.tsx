import React, { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';

interface PlayerTooltipProps {
    joinDate: string;
    joinDaysAgo: number;
    afkDates?: string;
    isAfk: boolean;
    children: React.ReactNode;
}

const PlayerTooltip: React.FC<PlayerTooltipProps> = ({
    joinDate,
    joinDaysAgo,
    afkDates,
    isAfk,
    children
}) => {
    const [isVisible, setIsVisible] = useState(false);
    const [coords, setCoords] = useState({ top: 0, left: 0 });
    const triggerRef = useRef<HTMLDivElement>(null);

    // Don't show tooltip if no data
    if (!joinDate && !isAfk) {
        return <>{children}</>;
    }

    const handleMouseEnter = () => {
        if (triggerRef.current) {
            const rect = triggerRef.current.getBoundingClientRect();
            setCoords({
                top: rect.top + window.scrollY - 10, // 10px spacing above element
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
                onMouseEnter={handleMouseEnter}
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
                        zIndex: 99999, // Max z-index
                        width: 'max-content',
                        minWidth: '200px',
                        boxShadow: '0 10px 30px rgba(0,0,0,0.9)',
                        pointerEvents: 'none',
                        animation: 'fadeIn 0.2s ease-out'
                    }}
                >
                    <div style={{ marginBottom: '8px', borderBottom: '1px solid rgba(255, 255, 255, 0.05)', paddingBottom: '6px' }}>
                        <div style={{ fontSize: '0.7rem', color: '#666', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Дата вступления</div>
                        <div style={{ fontSize: '0.9rem', color: '#ccc', fontWeight: 600 }}>
                            {joinDate || 'Неизвестно'}
                            {joinDaysAgo > 0 && <span style={{ color: 'var(--accent-ruby)', marginLeft: '6px', fontSize: '0.75rem' }}>({joinDaysAgo} дн. назад)</span>}
                        </div>
                    </div>

                    {isAfk && afkDates && (
                        <div>
                            <div style={{ fontSize: '0.7rem', color: '#666', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Период АФК</div>
                            <div style={{ fontSize: '0.9rem', color: 'var(--accent-ruby)', fontWeight: 600 }}>{afkDates}</div>
                        </div>
                    )}

                    {/* Arrow (Visual only, pointing down) */}
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
