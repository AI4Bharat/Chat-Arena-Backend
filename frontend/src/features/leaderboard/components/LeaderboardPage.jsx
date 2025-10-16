import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../../../shared/api/client';
import { endpoints } from '../../../shared/api/endpoints';
import { Trophy, TrendingUp, Award, Clock } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export function LeaderboardPage() {
  const navigate = useNavigate();
  const [selectedCategory, setSelectedCategory] = useState('overall');
  const [selectedPeriod, setSelectedPeriod] = useState('all_time');

  const { data: leaderboard, isLoading } = useQuery({
    queryKey: ['leaderboard', selectedCategory, selectedPeriod],
    queryFn: async () => {
      const response = await apiClient.get(endpoints.metrics.leaderboard, {
        params: { category: selectedCategory, period: selectedPeriod }
      });
      return response.data;
    },
  });

  const categories = [
    { id: 'overall', name: 'Overall', icon: Trophy },
    { id: 'creative_writing', name: 'Creative Writing', icon: Award },
    { id: 'coding', name: 'Coding', icon: TrendingUp },
    { id: 'reasoning', name: 'Reasoning', icon: Clock },
  ];

  const periods = [
    { id: 'all_time', name: 'All Time' },
    { id: 'weekly', name: 'This Week' },
    { id: 'daily', name: 'Today' },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-bold text-gray-900">Model Leaderboard</h1>
            <button
              onClick={() => navigate('/chat')}
              className="px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700"
            >
              Back to Chat
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Filters */}
        <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Category Filter */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Category
              </label>
              <div className="grid grid-cols-2 gap-2">
                {categories.map((category) => (
                  <button
                    key={category.id}
                    onClick={() => setSelectedCategory(category.id)}
                    className={`flex items-center gap-2 px-4 py-2 rounded-lg border ${
                      selectedCategory === category.id
                        ? 'border-orange-500 bg-orange-50 text-orange-700'
                        : 'border-gray-300 hover:bg-gray-50'
                    }`}
                  >
                    <category.icon size={16} />
                    {category.name}
                  </button>
                ))}
              </div>
            </div>

            {/* Period Filter */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Time Period
              </label>
              <div className="flex gap-2">
                {periods.map((period) => (
                  <button
                    key={period.id}
                    onClick={() => setSelectedPeriod(period.id)}
                    className={`flex-1 px-4 py-2 rounded-lg border ${
                      selectedPeriod === period.id
                        ? 'border-orange-500 bg-orange-50 text-orange-700'
                        : 'border-gray-300 hover:bg-gray-50'
                    }`}
                  >
                    {period.name}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Leaderboard Table */}
        <div className="bg-white rounded-lg shadow-sm overflow-hidden">
          {isLoading ? (
            <div className="p-8 text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-orange-600 mx-auto"></div>
            </div>
          ) : (
            <>
              <div className="hidden lg:block overflow-x-auto">
                <table className="min-w-full">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Rank
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Model
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Provider
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        ELO Rating
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Win Rate
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Total Comparisons
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {leaderboard?.map((model, index) => (
                      <tr key={model.id} className="hover:bg-gray-50">
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="flex items-center">
                            {index < 3 ? (
                              <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                                index === 0 ? 'bg-yellow-100 text-yellow-700' :
                                index === 1 ? 'bg-gray-100 text-gray-700' :
                                'bg-orange-100 text-orange-700'
                              }`}>
                                {index + 1}
                              </div>
                            ) : (
                              <span className="text-gray-500">{index + 1}</span>
                            )}
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="text-sm font-medium text-gray-900">{model.name}</div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="text-sm text-gray-500">{model.provider}</div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="text-sm text-gray-900">{model.elo_rating}</div>
                          <div className="text-xs text-gray-500">
                            {model.rating_change > 0 ? '+' : ''}{model.rating_change}
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="text-sm text-gray-900">
                            {((model.wins / (model.wins + model.losses + model.ties)) * 100).toFixed(1)}%
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="text-sm text-gray-500">
                            {model.wins + model.losses + model.ties}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Mobile Cards */}
              <div className="lg:hidden">
                {leaderboard?.map((model, index) => (
                  <div key={model.id} className="p-4 border-b border-gray-200 last:border-b-0">
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center gap-3">
                        {index < 3 ? (
                          <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                            index === 0 ? 'bg-yellow-100 text-yellow-700' :
                            index === 1 ? 'bg-gray-100 text-gray-700' :
                            'bg-orange-100 text-orange-700'
                          }`}>
                            {index + 1}
                          </div>
                        ) : (
                          <span className="text-gray-500 text-lg font-medium">{index + 1}</span>
                        )}
                        <div>
                          <div className="font-medium text-gray-900">{model.name}</div>
                          <div className="text-sm text-gray-500">{model.provider}</div>
                        </div>
                      </div>
                    </div>
                    
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <div className="text-gray-500 text-xs uppercase tracking-wide">ELO Rating</div>
                        <div className="font-medium text-gray-900">{model.elo_rating}</div>
                        <div className="text-xs text-gray-500">
                          {model.rating_change > 0 ? '+' : ''}{model.rating_change}
                        </div>
                      </div>
                      <div>
                        <div className="text-gray-500 text-xs uppercase tracking-wide">Win Rate</div>
                        <div className="font-medium text-gray-900">
                          {((model.wins / (model.wins + model.losses + model.ties)) * 100).toFixed(1)}%
                        </div>
                      </div>
                      <div className="col-span-2">
                        <div className="text-gray-500 text-xs uppercase tracking-wide">Total Comparisons</div>
                        <div className="font-medium text-gray-900">
                          {model.wins + model.losses + model.ties}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}