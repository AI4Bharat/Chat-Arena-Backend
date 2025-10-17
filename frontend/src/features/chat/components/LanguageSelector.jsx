import { useState, useRef, useEffect } from 'react';
import { ChevronDown, Check } from 'lucide-react';

const languages = [
  { value: 'en', label: 'English' }, { value: 'hi', label: 'Hindi' },
  { value: 'mr', label: 'Marathi' }, { value: 'ta', label: 'Tamil' },
  { value: 'te', label: 'Telugu' }, { value: 'kn', label: 'Kannada' },
  { value: 'gu', label: 'Gujarati' }, { value: 'pa', label: 'Punjabi' },
  { value: 'bn', label: 'Bengali' }, { value: 'ml', label: 'Malayalam' },
  { value: 'as', label: 'Assamese' }, { value: 'brx', label: 'Bodo' },
  { value: 'doi', label: 'Dogri' }, { value: 'ks', label: 'Kashmiri' },
  { value: 'mai', label: 'Maithili' }, { value: 'mni', label: 'Manipuri' },
  { value: 'ne', label: 'Nepali' }, { value: 'or', label: 'Odia' },
  { value: 'sd', label: 'Sindhi' }, { value: 'si', label: 'Sinhala' },
  { value: 'ur', label: 'Urdu' }, { value: 'sat', label: 'Santali' },
  { value: 'sa', label: 'Sanskrit' }, { value: 'gom', label: 'Goan Konkani' },
];

export function LanguageSelector({ value, onChange }) {
  const [isOpen, setIsOpen] = useState(false);
  const wrapperRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [wrapperRef]);

  const selectedLanguage = languages.find(lang => lang.value === value) || languages[0];

  return (
    <div className="relative w-32" ref={wrapperRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between text-left px-2 py-1 rounded-md text-sm text-gray-800 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-orange-500/50"
      >
        <span className="truncate">{selectedLanguage.label}</span>
        <ChevronDown size={16} className={`transition-transform duration-200 text-gray-500 ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div 
          className="absolute bottom-full mb-2 w-48 bg-white border border-gray-200 rounded-lg shadow-xl z-20 origin-bottom"
        >
          <div className="max-h-60 overflow-y-auto p-1">
            {languages.map(lang => (
              <button
                key={lang.value}
                onClick={() => {
                  onChange({ target: { value: lang.value } });
                  setIsOpen(false);
                }}
                className="w-full text-left flex items-center justify-between p-2 rounded-md hover:bg-gray-100 transition-colors text-sm"
              >
                <p className={`font-medium ${selectedLanguage.value === lang.value ? 'text-orange-600' : 'text-gray-800'}`}>
                  {lang.label}
                </p>
                {selectedLanguage.value === lang.value && <Check size={18} className="text-orange-500" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}