import { Bot, BrainCircuit, Sparkles, Cpu, Layers, Code } from 'lucide-react';

const ProviderIcon = ({ icon: Icon }) => (
  <Icon 
    className="h-6 w-6 text-orange-500/80 transition-opacity hover:text-orange-500/100" 
    strokeWidth={1.5} 
  />
);

export function NewChatLanding() {
  return (
    <div className="flex flex-col items-center text-center p-4 mb-8">
      <div className="flex items-center space-x-4 mb-6">
        <ProviderIcon icon={Bot} />
        <ProviderIcon icon={Sparkles} />
        <ProviderIcon icon={Layers} />
        <ProviderIcon icon={Code} />
        <ProviderIcon icon={Cpu} />
        <ProviderIcon icon={BrainCircuit} />
      </div>

      <h1 className="text-4xl md:text-5xl font-bold text-slate-800 tracking-tight">
        Find the{' '}
        <span className="bg-gradient-to-r from-orange-500 to-amber-500 bg-clip-text text-transparent">
          best AI for you
        </span>
      </h1>

      <p className="mt-4 max-w-2xl text-lg text-slate-600">
        Compare answers across top AI models, share your feedback and power our public leaderboard.
      </p>
    </div>
  );
}