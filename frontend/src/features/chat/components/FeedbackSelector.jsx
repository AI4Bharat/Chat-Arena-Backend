import { ArrowLeft, ArrowRight, ThumbsDown, ThumbsUp } from 'lucide-react';
import { motion } from 'framer-motion';

const Button = ({ children, onClick, onMouseEnter, className = '' }) => (
  <button
    onClick={onClick}
    onMouseEnter={onMouseEnter}
    className={`
      flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium 
      bg-white border border-gray-300 rounded-full shadow-sm 
      text-gray-700 
      hover:bg-gray-100 hover:border-gray-400 hover:shadow-md 
      focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-orange-500 
      transition-all duration-200
      ${className}
    `}
  >
    {children}
  </button>
);

export function FeedbackSelector({ onSelect, onHover }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}

      className="absolute bottom-20 left-0 right-0 z-10 flex justify-center"

      onMouseLeave={() => onHover(null)}
      style={{ pointerEvents: 'none' }}
    >
      <div
        className="flex items-center p-1 space-x-1 bg-gray-100 border border-gray-200/80 rounded-full"
        style={{ pointerEvents: 'auto' }}
      >
        <Button onClick={() => onSelect('model_a')} onMouseEnter={() => onHover('model_a')}>
          <ArrowLeft size={16} /> Left is Better
        </Button>
        <Button onClick={() => onSelect('tie')} onMouseEnter={() => onHover('tie')}>
          <ThumbsUp size={16} /> Both are good
        </Button>
        <Button onClick={() => onSelect('both_bad')} onMouseEnter={() => onHover('both_bad')}>
          <ThumbsDown size={16} /> Both are Bad
        </Button>
        <Button onClick={() => onSelect('model_b')} onMouseEnter={() => onHover('model_b')}>
          <ArrowRight size={16} />Right is Better
        </Button>
      </div>
    </motion.div>
  );
}