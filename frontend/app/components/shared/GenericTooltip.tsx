import React, { useState, useRef } from 'react';
import { createPortal } from 'react-dom';

interface GenericTooltipProps {
    title?: string;
    content: string | string[];
    children: React.ReactNode;
}

const GenericTooltip: React.FC<GenericTooltipProps> = ({ title, content, children }) => {
    const [isVisible, setIsVisible] = useState(false);
    const [coords, setCoords] = useState({ top: 0, left: 0 });
    const triggerRef = useRef<HTMLDivElement>(null);

    const handleMouseEnter = () => {
        if (triggerRef.current) {
            const rect = triggerRef.current.getBoundingClientRect();
            setCoords({
                top: rect.top + window.scrollY - 8,
                left: rect.left + window.scrollX + (rect.width / 2)
            });
            setIsVisible(true);
        }
    };

    const contentArray = Array.isArray(content) ? content : [content];

    return (
        <>
            <div
                ref={triggerRef}
                style={{ position: 'relative', display: 'inline-block', cursor: 'help' }}
                onMouseEnter={handleMouseEnter}
                onMouseLeave={() => setIsVisible(false)}
            >
                {children}
            </div>

            {isVisible && createPortal(
                <div
                    style={{
                        position: 'absolute',
                        top: coords.top,
                        left: coords.left,
                        transform: 'translate(-50%, -100%)',
                        marginBottom: '10px',
                        background: 'rgba(15, 15, 15, 0.98)',
                        border: '1px solid rgba(255, 255, 255, 0.12)',
                        borderRadius: '6px',
                        padding: '10px 14px',
                        zIndex: 100000,
                        width: 'max-content',
                        minWidth: '160px',
                        boxShadow: '0 8px 25px rgba(0,0,0,0.8)',
                        pointerEvents: 'none',
                        animation: 'tooltipFadeIn 0.15s ease-out'
                    }}
                >
                    {title && (
                        <div style={{
                            fontSize: '0.7rem',
                            color: '#666',
                            textTransform: 'uppercase',
                            letterSpacing: '0.05em',
                            marginBottom: '6px',
                            borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                            paddingBottom: '4px'
                        }}>
                            {title}
                        </div>
                    )}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                        {contentArray.length > 0 ? contentArray.map((item, i) => (
                            <div key={i} style={{ fontSize: '0.85rem', color: '#ccc', fontWeight: 500 }}>
                                {item}
                            </div>
                        )) : (
                            <div style={{ fontSize: '0.85rem', color: '#444' }}>Нет данных</div>
                        )}
                    </div>

                    {/* Arrow */}
                    <div style={{
                        position: 'absolute',
                        top: '100%',
                        left: '50%',
                        transform: 'translateX(-50%)',
                        width: 0,
                        height: 0,
                        borderLeft: '5px solid transparent',
                        borderRight: '5px solid transparent',
                        borderTop: '5px solid rgba(255, 255, 255, 0.12)'
                    }} />

                    <style>{`
                        @keyframes tooltipFadeIn {
                            from { opacity: 0; transform: translate(-50%, -95%); }
                            to { opacity: 1; transform: translate(-50%, -100%); }
                        }
                    `}</style>
                </div>,
                document.body
            )}
        </>
    );
};

export default GenericTooltip;
