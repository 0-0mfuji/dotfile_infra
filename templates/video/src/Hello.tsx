import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';

// 日本語の字幕が豆腐 (□) にならないことを確認するための最小のコンポジション。
// 豆腐になるときは、video-dev に fonts-noto-cjk が入っていない (provision/run video-dev)。
export const Hello: React.FC<{text: string}> = ({text}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 20], [0, 1], {extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{backgroundColor: '#101820', justifyContent: 'center', alignItems: 'center', padding: 160, textAlign: 'center'}}>
      <div style={{color: 'white', fontSize: 72, opacity, fontFamily: '"Noto Sans CJK JP", sans-serif'}}>{text}</div>
    </AbsoluteFill>
  );
};
