import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { TutorComposer } from './TutorComposer';

describe('TutorComposer', () => {
  it('does not send when Enter is pressed during IME composition', () => {
    const onSend = vi.fn();

    render(
      <TutorComposer
        input="ni"
        isSending={false}
        language="en"
        quickActions={[]}
        conversationNotice={null}
        tokens={
          {
            surfaceElevated: '#fff',
            borderSubtle: '1px solid #ddd',
            shadowSoft: 'none',
            textPrimary: '#111',
            textSecondary: '#666',
            textInverted: '#fff',
            disabledSurface: '#ccc',
            disabledText: '#999',
          } as never
        }
        t={(zh, en) => en ?? zh}
        onInputChange={() => undefined}
        onSend={onSend}
      />,
    );

    const input = screen.getByPlaceholderText('Ask anything');
    fireEvent.keyDown(input, {
      key: 'Enter',
      code: 'Enter',
      keyCode: 229,
      nativeEvent: { isComposing: true },
    });

    expect(onSend).not.toHaveBeenCalled();
  });
});
