export function Loading({ size = 'default', className = '' }) {
    const sizeClasses = {
      small: 'w-4 h-4',
      default: 'w-8 h-8',
      large: 'w-12 h-12',
    };
  
    return (
      <div className={`flex items-center justify-center ${className}`}>
        <div
          className={`animate-spin rounded-full border-b-2 border-orange-600 ${sizeClasses[size]}`}
        />
      </div>
    );
  }
  
  export function LoadingOverlay({ message = 'Loading...' }) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
        <div className="bg-white rounded-lg p-6 flex flex-col items-center">
          <Loading size="large" />
          <p className="mt-4 text-gray-600">{message}</p>
        </div>
      </div>
    );
  }