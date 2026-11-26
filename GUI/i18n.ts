import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import commonEN from './translations/en/common.json';
import commonET from './translations/et/common.json';

// Keep <html lang> in sync with the active language so screen readers and
// browser translation treat the page as the language actually shown.
// Registered before init() so it also runs for the initially detected language.
i18n.on('languageChanged', () => {
  document.documentElement.lang = i18n.resolvedLanguage ?? 'et';
});

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    debug: import.meta.env.NODE_ENV === 'development',
    fallbackLng: 'et',
    supportedLngs: ['et','en'],
    resources: {
      en: {
        common: commonEN,
      },
      et: {
        common: commonET,
      },
    },
    defaultNS: 'common',
    // Keep t() typed and behaving as string-only (see src/types/i18next.d.ts).
    returnNull: false,
  });

export default i18n;
