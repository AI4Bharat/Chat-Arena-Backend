import { useState, useRef, useEffect } from 'react';
import { ChevronDown, Check, Search } from 'lucide-react';

function useOutsideAlerter(ref, callback) {
  useEffect(() => {
    function handleClickOutside(event) {
      if (ref.current && !ref.current.contains(event.target)) callback();
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [ref, callback]);
}

export function ModelDropdown({ models, selectedModelId, onSelect, disabled = false, fullWidth = false }) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const wrapperRef = useRef(null);
  useOutsideAlerter(wrapperRef, () => setIsOpen(false));

  const selectedModel = models.find(m => m.id === selectedModelId);

  const filteredModels = models.filter(model =>
    model.display_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    model.provider.toLowerCase().includes(searchTerm.toLowerCase())
  );
  
  useEffect(() => {
    if (!isOpen) setSearchTerm('');
  }, [isOpen]);

  const buttonText = selectedModel?.display_name || '...'; 

  const containerWidthClass = fullWidth ? 'w-64 sm:w-56' : 'w-40 sm:w-56';

  return (
    <div className={`relative ${containerWidthClass}`} ref={wrapperRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        disabled={disabled}
        className="w-full flex items-center justify-between text-left p-2 bg-white border border-transparent rounded-md text-sm sm:text-base text-gray-800 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        <span className="truncate font-medium">{buttonText}</span>
        <ChevronDown size={16} className={`transition-transform duration-200 text-gray-500 ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div 
          className="absolute top-full mt-2 w-full bg-white border border-gray-200 rounded-lg shadow-xl z-20
                     origin-top transition-all duration-200 ease-out
                     opacity-100 scale-100"
        >
          <div className="p-2 border-b border-gray-200">
            <div className="relative">
              <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                placeholder="Search models..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                autoFocus
                className="w-full bg-gray-50 border border-gray-200 rounded-md pl-10 pr-3 py-2 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-orange-400"
              />
            </div>
          </div>
          <div className="max-h-60 overflow-y-auto p-1">
            {filteredModels.map(model => (
              <button
                key={model.id}
                onClick={() => { onSelect(model); setIsOpen(false); }}
                className={`w-full text-left flex items-center justify-between p-2.5 rounded-md hover:bg-gray-100 transition-colors ${selectedModelId === model.id ? 'bg-gray-100' : ''}`}
              >
                <p className="text-sm font-medium text-gray-800">{model.display_name}</p>
                {selectedModelId === model.id && <Check size={18} className="text-orange-500" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}