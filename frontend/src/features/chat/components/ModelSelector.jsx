import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSelector, useDispatch } from 'react-redux';
import { apiClient } from '../../../shared/api/client';
import { endpoints } from '../../../shared/api/endpoints';
import { createSession } from '../store/chatSlice';
import { ChevronDown, Zap, GitCompare, Shuffle } from 'lucide-react';

export function ModelSelector() {
  const dispatch = useDispatch();
  const { activeSession } = useSelector((state) => state.chat);
  const [mode, setMode] = useState(activeSession?.mode || 'direct');
  const [selectedModels, setSelectedModels] = useState({
    modelA: activeSession?.model_a?.id || null,
    modelB: activeSession?.model_b?.id || null,
  });
  const [isOpen, setIsOpen] = useState(false);

  const { data: models = [], isLoading } = useQuery({
    queryKey: ['models'],
    queryFn: async () => {
      const response = await apiClient.get(endpoints.models.list);
      return response.data;
    },
  });

  const handleModeChange = (newMode) => {
    setMode(newMode);
    if (newMode === 'direct') {
      setSelectedModels({ ...selectedModels, modelB: null });
    } else if (newMode === 'random') {
      setSelectedModels({ modelA: null, modelB: null });
    }
  };

  const handleModelSelect = (model, slot = 'modelA') => {
    setSelectedModels({ ...selectedModels, [slot]: model.id });
  };

  const handleStartSession = async () => {
    await dispatch(createSession({
      mode,
      modelA: selectedModels.modelA,
      modelB: selectedModels.modelB,
    }));
    setIsOpen(false);
  };

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
      >
        {mode === 'direct' && <Zap size={16} />}
        {mode === 'compare' && <GitCompare size={16} />}
        {mode === 'random' && <Shuffle size={16} />}
        <span>
          {mode === 'direct' && selectedModels.modelA
            ? models.find(m => m.id === selectedModels.modelA)?.name
            : mode === 'compare' && selectedModels.modelA && selectedModels.modelB
            ? 'Compare Mode'
            : mode === 'random'
            ? 'Random Mode'
            : 'New Chat'}
        </span>
        <ChevronDown size={16} />
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
          <div className="absolute right-0 mt-2 w-96 bg-white rounded-lg shadow-lg border border-gray-200 z-20">
            {/* Mode Selector */}
            <div className="p-4 border-b border-gray-200">
              <div className="flex gap-2">
                <button
                  onClick={() => handleModeChange('direct')}
                  className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg ${
                    mode === 'direct' ? 'bg-orange-100 text-orange-700' : 'bg-gray-100'
                  }`}
                >
                  <Zap size={16} />
                  Direct
                </button>
                <button
                  onClick={() => handleModeChange('compare')}
                  className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg ${
                    mode === 'compare' ? 'bg-orange-100 text-orange-700' : 'bg-gray-100'
                  }`}
                >
                  <GitCompare size={16} />
                  Compare
                </button>
                <button
                  onClick={() => handleModeChange('random')}
                  className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg ${
                    mode === 'random' ? 'bg-orange-100 text-orange-700' : 'bg-gray-100'
                  }`}
                >
                  <Shuffle size={16} />
                  Random
                </button>
              </div>
            </div>

            {/* Model Selection */}
            {mode !== 'random' && (
              <div className="p-4 max-h-96 overflow-y-auto">
                {/* Model A */}
                <div className="mb-4">
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    {mode === 'direct' ? 'Select Model' : 'Model A'}
                  </label>
                  <div className="space-y-2">
                    {models.map((model) => (
                      <button
                        key={model.id}
                        onClick={() => handleModelSelect(model, 'modelA')}
                        className={`w-full text-left p-3 rounded-lg border ${
                          selectedModels.modelA === model.id
                            ? 'border-orange-500 bg-orange-50'
                            : 'border-gray-300 hover:bg-gray-50'
                        }`}
                      >
                        <div className="font-medium">{model.name}</div>
                        <div className="text-sm text-gray-500">{model.provider}</div>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Model B for Compare Mode */}
                {mode === 'compare' && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Model B
                    </label>
                    <div className="space-y-2">
                      {models
                        .filter((m) => m.id !== selectedModels.modelA)
                        .map((model) => (
                          <button
                            key={model.id}
                            onClick={() => handleModelSelect(model, 'modelB')}
                            className={`w-full text-left p-3 rounded-lg border ${
                              selectedModels.modelB === model.id
                                ? 'border-orange-500 bg-orange-50'
                                : 'border-gray-300 hover:bg-gray-50'
                            }`}
                          >
                            <div className="font-medium">{model.name}</div>
                            <div className="text-sm text-gray-500">{model.provider}</div>
                          </button>
                        ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Start Button */}
            <div className="p-4 border-t border-gray-200">
              <button
                onClick={handleStartSession}
                disabled={
                  (mode === 'direct' && !selectedModels.modelA) ||
                  (mode === 'compare' && (!selectedModels.modelA || !selectedModels.modelB))
                }
                className="w-full px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
              >
                {mode === 'random' ? 'Start Random Session' : 'Start Session'}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}