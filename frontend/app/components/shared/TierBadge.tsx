import React from 'react';

interface TierBadgeProps {
    tier: string; // "S", "A", "B", "C", "D"
    type: 'valor' | 'gold';
}

export default function TierBadge({ tier, type }: TierBadgeProps) {
    // Map Tier to Color (matching style.css logic if implicit, or explicit logic)
    /* 
      Usually in this project:
      S = Gold/Ruby
      A = Purple
      B = Blue
      C = Green
      D = Grey
    */

    let color = '#ccc';
    let glow = 'none';

    switch (tier) {
        case 'S':
            color = '#FFD700'; // Gold
            glow = '0 0 8px rgba(255, 215, 0, 0.6)';
            break;
        case 'A':
            color = '#A020F0'; // Purple
            glow = '0 0 6px rgba(160, 32, 240, 0.5)';
            break;
        case 'B':
            color = '#1E90FF'; // Blue
            glow = '0 0 6px rgba(30, 144, 255, 0.5)';
            break;
        case 'C':
            color = '#32CD32'; // Lime
            glow = 'none';
            break;
        case 'D':
        default:
            color = '#888';
            glow = 'none';
            break;
    }

    return (
        <span
            style={{
                color,
                textShadow: glow,
                fontWeight: 'bold',
                fontFamily: "'Cinzel', serif"
            }}
        >
            {tier}
        </span>
    );
}
