export function SidebarItem({ icon: Icon, text, active, isOpen, onClick, bordered = false }) {
    return (
      <button
        onClick={onClick}
        className={`
          relative flex items-center w-full h-11
          font-medium rounded-lg cursor-pointer
          transition-colors group my-1 border
          ${isOpen ? 'px-4' : 'justify-center'}
          ${active
            ? 'bg-orange-100 text-orange-800 border-orange-200'
            : bordered
            ? 'border-2 border-orange-400 text-gray-600 hover:bg-orange-50'
            : 'border-transparent text-gray-600 hover:bg-gray-100'
          }
        `}
      >
        <Icon size={20} />
        <span className={`overflow-hidden transition-all ${isOpen ? "w-40 ml-3" : "w-0"}`}>
          {text}
        </span>
  
        {!isOpen && (
          <div className={`
            absolute left-full rounded-md px-2 py-1 ml-6
            bg-gray-800 text-white text-sm
            invisible opacity-20 -translate-x-3 transition-all
            group-hover:visible group-hover:opacity-100 group-hover:translate-x-0
          `}>
            {text}
          </div>
        )}
      </button>
    );
  }