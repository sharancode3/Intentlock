import React from 'react';

interface IntentLockLogoProps {
  className?: string;
  size?: number;
}

export const IntentLockLogo: React.FC<IntentLockLogoProps> = ({
  className = '',
  size = 32,
}) => {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`shrink-0 ${className}`}
      aria-hidden="true"
    >
      {/* Outer Vault Shield Contour */}
      <path
        d="M16 2.5L27 6.5V14.5C27 21.5 22 27 16 29.5C10 27 5 21.5 5 14.5V6.5L16 2.5Z"
        fill="#1D4ED8"
        stroke="#1E40AF"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
      {/* Subtle Inner Protective Contour */}
      <path
        d="M16 4.5L25 7.8V14.5C25 20.2 21 24.8 16 27C11 24.8 7 20.2 7 14.5V7.8L16 4.5Z"
        fill="#2563EB"
      />
      {/* Concentric Biometric Soundwave Bars */}
      <rect x="10.5" y="13.5" width="1.5" height="4" rx="0.75" fill="#BFDBFE" />
      <rect x="13" y="11.5" width="1.5" height="8" rx="0.75" fill="#DBEAFE" />
      <rect x="17.5" y="11.5" width="1.5" height="8" rx="0.75" fill="#DBEAFE" />
      <rect x="20" y="13.5" width="1.5" height="4" rx="0.75" fill="#BFDBFE" />
      
      {/* Central Vault Keyhole Core */}
      <circle cx="16" cy="14" r="2.2" fill="#FFFFFF" />
      <path
        d="M14.8 14.8L14.2 19.5H17.8L17.2 14.8C16.8 15.1 16.4 15.2 16 15.2C15.6 15.2 15.2 15.1 14.8 14.8Z"
        fill="#FFFFFF"
      />
    </svg>
  );
};
