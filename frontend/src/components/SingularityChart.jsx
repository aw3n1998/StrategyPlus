import React, { useEffect, useRef } from 'react';
import { TrendingUp, TrendingDown, Zap } from 'lucide-react';

export const SingularityChart = ({ status, selectedSymbol, symbols }) => {
  const canvasRef = useRef(null);
  const animationRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    let time = 0;

    const draw = () => {
      const width = canvas.width;
      const height = canvas.height;
      
      ctx.fillStyle = 'rgba(0, 0, 0, 0.1)';
      ctx.fillRect(0, 0, width, height);
      
      const centerX = width / 2;
      const centerY = height / 2;
      
      for (let i = 0; i < 3; i++) {
        const radius = 50 + Math.sin(time * 0.02 + i) * 20 + i * 30;
        const gradient = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, radius);
        gradient.addColorStop(0, 'rgba(212, 175, 55, 0.3)');
        gradient.addColorStop(0.5, 'rgba(212, 175, 55, 0.1)');
        gradient.addColorStop(1, 'rgba(212, 175, 55, 0)');
        
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        ctx.fillStyle = gradient;
        ctx.fill();
      }
      
      ctx.strokeStyle = 'rgba(212, 175, 55, 0.5)';
      ctx.lineWidth = 1;
      for (let i = 0; i < 8; i++) {
        const angle = (time * 0.01) + (i * Math.PI / 4);
        const length = 80 + Math.sin(time * 0.03 + i) * 20;
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.lineTo(
          centerX + Math.cos(angle) * length,
          centerY + Math.sin(angle) * length
        );
        ctx.stroke();
      }
      
      ctx.beginPath();
      ctx.arc(centerX, centerY, 8, 0, Math.PI * 2);
      ctx.fillStyle = '#d4af37';
      ctx.shadowColor = '#d4af37';
      ctx.shadowBlur = 20;
      ctx.fill();
      ctx.shadowBlur = 0;
      
      time++;
      animationRef.current = requestAnimationFrame(draw);
    };

    const resize = () => {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    };
    
    resize();
    window.addEventListener('resize', resize);
    draw();

    return () => {
      window.removeEventListener('resize', resize);
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, []);

  const symbol = selectedSymbol || symbols?.[0];
  const data = symbol ? status?.[symbol] : null;
  const price = data?.price || 0;
  const direction = data?.position?.direction;

  return (
    <div className="bg-quant-black-card border border-quant-black-border rounded-xl overflow-hidden relative">
      <div className="absolute inset-0">
        <canvas ref={canvasRef} className="w-full h-full" />
      </div>
      
      <div className="relative z-10 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-black uppercase tracking-widest text-white flex items-center gap-2">
            <Zap size={16} className="text-quant-gold animate-pulse" />
            Singularity Core
          </h3>
          {direction && (
            <span className={`flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold ${
              direction === 'long' 
                ? 'bg-green-500/20 text-green-500' 
                : 'bg-red-500/20 text-red-500'
            }`}>
              {direction === 'long' ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
              {direction.toUpperCase()}
            </span>
          )}
        </div>
        
        <div className="text-center py-8">
          <p className="text-[10px] text-gray-500 uppercase tracking-widest mb-2">Current Price</p>
          <p className="text-4xl font-black italic text-white tracking-tighter">
            ${price?.toLocaleString() || '---'}
          </p>
        </div>
        
        <div className="grid grid-cols-3 gap-4 mt-4">
          <div className="text-center p-3 bg-black/40 rounded-lg border border-white/5">
            <p className="text-[8px] text-gray-500 uppercase">Entry</p>
            <p className="text-sm font-bold text-white">
              {data?.position?.entry_price?.toFixed(2) || '---'}
            </p>
          </div>
          <div className="text-center p-3 bg-black/40 rounded-lg border border-white/5">
            <p className="text-[8px] text-gray-500 uppercase">Stop Loss</p>
            <p className="text-sm font-bold text-red-400">
              {data?.position?.stop_loss?.toFixed(2) || '---'}
            </p>
          </div>
          <div className="text-center p-3 bg-black/40 rounded-lg border border-white/5">
            <p className="text-[8px] text-gray-500 uppercase">Take Profit</p>
            <p className="text-sm font-bold text-green-400">
              {data?.position?.tp1?.toFixed(2) || '---'}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
