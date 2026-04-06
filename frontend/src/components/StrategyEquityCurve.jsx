import React from 'react';
import { 
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer 
} from 'recharts';

const StrategyEquityCurve = ({ equityCurveByStrategy, strategies }) => {
  if (!equityCurveByStrategy || Object.keys(equityCurveByStrategy).length === 0) {
    return (
      <div className="bg-quant-black-card border border-quant-black-border rounded-xl p-6">
        <h3 className="text-sm font-black text-white mb-4">策略收益曲线</h3>
        <p className="text-gray-500 text-xs">等待交易数据...</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {Object.entries(equityCurveByStrategy).map(([strategyId, curve]) => {
        if (!curve || !Array.isArray(curve) || curve.length === 0) {
          return (
            <div key={strategyId} className="bg-quant-black-card border border-quant-black-border rounded-xl p-4">
              <h3 className="text-sm font-black text-white mb-2">
                {strategies?.[strategyId]?.name || strategyId}
              </h3>
              <p className="text-gray-500 text-xs">暂无交易数据</p>
            </div>
          );
        }
        
        const totalPnl = curve.reduce((sum, p) => sum + (p.trade_pnl || 0), 0);
        
        return (
          <div key={strategyId} className="bg-quant-black-card border border-quant-black-border rounded-xl p-4">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-sm font-black text-white">
                {strategy?.name || strategyId}
              </h3>
              <span className={`text-xs font-bold ${totalPnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                {totalPnl >= 0 ? '+' : ''}{totalPnl.toFixed(2)} USDT
              </span>
            </div>
            
            {curve.length > 0 ? (
              <ResponsiveContainer width="100%" height={150}>
                <AreaChart data={curve} margin={{ top: 5, right: 5, left: 0, bottom: 5 }}>
                  <defs>
                    <linearGradient id={`gradient-${strategyId}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#d4af37" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#d4af37" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#333" vertical={false} />
                  <XAxis 
                    dataKey="time" 
                    tick={{ fontSize: 8, fill: '#666' }} 
                    axisLine={{ stroke: '#333' }}
                    tickLine={false}
                  />
                  <YAxis 
                    tick={{ fontSize: 8, fill: '#666' }}
                    axisLine={{ stroke: '#333' }}
                    tickLine={false}
                    tickFormatter={(v) => v.toFixed(1)}
                  />
                  <Tooltip 
                    contentStyle={{ 
                      background: '#1a1a1a', 
                      border: '1px solid #333',
                      borderRadius: '8px',
                      fontSize: '10px'
                    }}
                    labelStyle={{ color: '#888' }}
                    formatter={(value) => [`${value.toFixed(2)} USDT`, 'PnL']}
                  />
                  <Area 
                    type="monotone" 
                    dataKey="cumulative_pnl" 
                    stroke="#d4af37" 
                    fill={`url(#gradient-${strategyId})`}
                    strokeWidth={1.5}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-gray-500 text-xs text-center py-8">暂无交易数据</p>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default StrategyEquityCurve;
