import React from 'react';

interface ClassIconProps {
    classId: number;
    className?: string; // Additional CSS classes
    size?: number;
}

export default function ClassIcon({ classId, className = "", size = 24 }: ClassIconProps) {
    if (classId < 0) {
        // Return placeholder for unknown/invalid class (negative values only)
        return <span style={{ width: size, height: size, display: 'inline-block' }}></span>;
    }
    return (
        <img
            src={`/icons/${classId}.png`}
            alt={`Class ${classId}`}
            width={size}
            height={size}
            className={`class-icon ${className}`}
            title={`Class ${classId}`}
            onError={(e) => { e.currentTarget.style.display = 'none'; }}
        />
    );
}
