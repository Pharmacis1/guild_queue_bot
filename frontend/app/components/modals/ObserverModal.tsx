import React, { useEffect, useState } from 'react';
import { fetchObserver } from '@/lib/api';

interface ObserverModalProps {
    roleId: number;
    nickname: string;
    onClose: () => void;
}

const ObserverModal: React.FC<ObserverModalProps> = ({ roleId, nickname, onClose }) => {
    const [loading, setLoading] = useState(true);
    const [htmlContent, setHtmlContent] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [isClosing, setIsClosing] = useState(false);

    const handleClose = () => {
        setIsClosing(true);
        setTimeout(() => {
            onClose();
        }, 200);
    };

    useEffect(() => {
        setLoading(true);
        setError(null);
        fetchObserver(roleId)
            .then(data => {
                if (data.status === 'ok') {
                    setHtmlContent(data.html);
                } else {
                    setError(data.message || 'Failed to load observer data');
                }
            })
            .catch(err => {
                console.error("Observer Error", err);
                setError("Network or Server Error");
            })
            .finally(() => setLoading(false));

        // Prevent background scrolling
        document.body.style.overflow = 'hidden';
        return () => {
            document.body.style.overflow = '';
        };
    }, [roleId]);

    // Close on escape
    useEffect(() => {
        const handleEsc = (e: KeyboardEvent) => {
            if (e.key === 'Escape') handleClose();
        };
        document.addEventListener('keydown', handleEsc);
        return () => document.removeEventListener('keydown', handleEsc);
    }, [handleClose]);

    return (
        <div
            className={`modal fade show d-block ${isClosing ? 'modal-animate-out' : ''}`}
            tabIndex={-1}
            style={{ backgroundColor: 'rgba(0,0,0,0.9)', zIndex: 1060, transition: 'opacity 0.2s' }}
            onClick={(e) => {
                // Close if clicking backend (outside modal-dialog)
                if (e.target === e.currentTarget) handleClose();
            }}
        >
            <div className={`modal-dialog modal-xl modal-dialog-centered ${isClosing ? 'modal-animate-out' : 'modal-animate-in'}`} style={{ maxWidth: '90vw' }}>
                <div className="modal-content" style={{ background: 'transparent', border: 'none' }}>

                    {/* Header */}
                    <div
                        style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            marginBottom: '1rem',
                            padding: '1rem',
                            background: 'rgba(20, 20, 20, 0.9)',
                            borderRadius: '8px',
                            border: '1px solid #333',
                            position: 'relative'
                        }}
                    >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span style={{ fontSize: '1.5rem' }}>👁️</span>
                            <h4 style={{ margin: 0, color: '#fff' }}>Equipment: {nickname}</h4>
                        </div>
                        <button
                            onClick={handleClose}
                            style={{
                                background: 'transparent',
                                border: '1px solid clearfix',
                                color: '#fff',
                                fontSize: '1.5rem',
                                cursor: 'pointer',
                                lineHeight: 0.5,
                                padding: '5px 10px',
                                borderRadius: '4px',
                                transition: 'background 0.2s',
                            }}
                            className="btn-close-custom"
                            onMouseOver={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.1)'}
                            onMouseOut={(e) => e.currentTarget.style.background = 'transparent'}
                        >
                            &times;
                        </button>
                    </div>

                    {/* Content */}
                    <div className="position-relative" style={{ minHeight: '600px', display: 'flex', justifyContent: 'center', alignItems: 'center', position: 'relative' }}>
                        {loading && (
                            <div style={{ textAlign: 'center', color: '#fff' }}>
                                <div style={{
                                    display: 'inline-block',
                                    width: '2rem',
                                    height: '2rem',
                                    verticalAlign: 'text-bottom',
                                    border: '.25em solid currentColor',
                                    borderRightColor: 'transparent',
                                    borderRadius: '50%',
                                    animation: 'spinner-border .75s linear infinite',
                                    marginBottom: '1rem'
                                }}></div>
                                <style>{`@keyframes spinner-border { 100% { transform: rotate(360deg); } }`}</style>
                                <div>Loading PWOBS data... (This may take a few seconds)</div>
                            </div>
                        )}

                        {error && (
                            <div style={{
                                width: '50%',
                                textAlign: 'center',
                                color: '#721c24',
                                backgroundColor: '#f8d7da',
                                borderColor: '#f5c6cb',
                                padding: '1rem',
                                borderRadius: '0.25rem'
                            }}>
                                <h4>Error</h4>
                                <p>{error}</p>
                                <button
                                    onClick={onClose}
                                    style={{
                                        color: '#721c24',
                                        backgroundColor: 'transparent',
                                        backgroundImage: 'none',
                                        borderColor: '#721c24',
                                        border: '1px solid',
                                        padding: '0.375rem 0.75rem',
                                        borderRadius: '0.25rem',
                                        cursor: 'pointer',
                                        marginTop: '0.5rem'
                                    }}
                                >Close</button>
                            </div>
                        )}

                        {!loading && !error && htmlContent && (
                            <div
                                style={{
                                    width: '100%',
                                    height: '80vh',
                                    overflow: 'auto',
                                    borderRadius: '8px',
                                    position: 'relative' // For absolute tooltips inside 
                                }}
                                dangerouslySetInnerHTML={{ __html: htmlContent }}
                            />
                        )}
                    </div>

                </div>
            </div>
        </div>
    );
};

export default ObserverModal;
