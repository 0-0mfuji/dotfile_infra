import {Composition} from 'remotion';
import {Hello} from './Hello';

export const Root: React.FC = () => {
  return (
    <Composition
      id="Hello"
      component={Hello}
      durationInFrames={150}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{text: 'こんにちは、ずんだもんなのだ。日本語フォントの確認です。'}}
    />
  );
};
