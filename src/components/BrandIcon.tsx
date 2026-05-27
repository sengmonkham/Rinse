import React from 'react';

interface BrandIconProps {
  platform: 'twitter' | 'instagram' | 'youtube';
  size?: number;
  className?: string;
  style?: React.CSSProperties;
}

export const BrandIcon: React.FC<BrandIconProps> = ({ 
  platform, 
  size = 16, 
  className = '', 
  style = {} 
}) => {
  switch (platform) {
    case 'twitter':
      return (
        <svg 
          viewBox="0 0 24 24" 
          width={size} 
          height={size} 
          fill="currentColor" 
          className={className}
          style={style}
        >
          <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
        </svg>
      );
    case 'instagram':
      return (
        <svg 
          viewBox="0 0 24 24" 
          width={size} 
          height={size} 
          fill="none" 
          stroke="currentColor" 
          strokeWidth="2" 
          strokeLinecap="round" 
          strokeLinejoin="round" 
          className={className}
          style={style}
        >
          <rect width="20" height="20" x="2" y="2" rx="5" ry="5" />
          <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
          <line x1="17.5" x2="17.51" y1="6.5" y2="6.5" />
        </svg>
      );
    case 'youtube':
      return (
        <svg 
          viewBox="0 0 24 24" 
          width={size} 
          height={size} 
          fill="none" 
          stroke="currentColor" 
          strokeWidth="2" 
          strokeLinecap="round" 
          strokeLinejoin="round" 
          className={className}
          style={style}
        >
          <path d="M2.5 17a24.12 24.12 0 0 1 0-10 2 2 0 0 1 1.4-1.4 49.56 49.56 0 0 1 16.2 0A2 2 0 0 1 21.5 7a24.12 24.12 0 0 1 0 10 2 2 0 0 1-1.4 1.4 49.55 49.55 0 0 1-16.2 0A2 2 0 0 1 2.5 17z" />
          <polygon points="9.75 15.02 15.5 12 9.75 8.98 9.75 15.02" fill="currentColor" />
        </svg>
      );
    default:
      return null;
  }
};
