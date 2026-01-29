// Electric Bolt SVG Icon for loading animation
const ElectricBoltIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ width: 32, height: 32 }}>
    <path
      d="M13 2L3 14H12L11 22L21 10H12L13 2Z"
      fill="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
)

export default function LoadingSpinner() {
  return (
    <div className="loading-container" style={{
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      alignItems: 'center',
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #0a1628 0%, #163860 50%, #0f2744 100%)'
    }}>
      {/* Animated Logo */}
      <div style={{
        width: 64,
        height: 64,
        background: 'linear-gradient(135deg, #06b6d4 0%, #2563eb 100%)',
        borderRadius: 16,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'white',
        boxShadow: '0 0 40px rgba(6, 182, 212, 0.4)',
        animation: 'pulse 2s ease-in-out infinite'
      }}>
        <ElectricBoltIcon />
      </div>

      {/* Loading Text */}
      <div style={{
        marginTop: 24,
        color: 'rgba(255, 255, 255, 0.8)',
        fontSize: 14,
        fontWeight: 500,
        letterSpacing: '0.5px'
      }}>
        加载中...
      </div>

      {/* Loading Bar */}
      <div style={{
        marginTop: 16,
        width: 120,
        height: 3,
        background: 'rgba(255, 255, 255, 0.1)',
        borderRadius: 2,
        overflow: 'hidden'
      }}>
        <div style={{
          width: '40%',
          height: '100%',
          background: 'linear-gradient(90deg, #06b6d4, #2563eb)',
          borderRadius: 2,
          animation: 'loadingBar 1.5s ease-in-out infinite'
        }} />
      </div>

      {/* Keyframe animations */}
      <style>{`
        @keyframes pulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.05); opacity: 0.9; }
        }
        @keyframes loadingBar {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(350%); }
        }
      `}</style>
    </div>
  )
}
