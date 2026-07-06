import { describe, expect, it } from 'vitest';

import { tutorQueryKeys } from './tutorQueryKeys';

describe('tutorQueryKeys', () => {
  it('returns stable keys for static tutor resources', () => {
    expect(tutorQueryKeys.profiles()).toEqual(['tutor', 'profiles']);
    expect(tutorQueryKeys.materials()).toEqual(['tutor', 'materials']);
  });

  it('includes search terms in the conversations key', () => {
    expect(tutorQueryKeys.conversations('')).toEqual(['tutor', 'conversations', { search: '' }]);
    expect(tutorQueryKeys.conversations('bayes')).toEqual([
      'tutor',
      'conversations',
      { search: 'bayes' },
    ]);
  });

  it('includes the conversation id in detail keys', () => {
    expect(tutorQueryKeys.conversation(42)).toEqual(['tutor', 'conversation', 42]);
  });
});
