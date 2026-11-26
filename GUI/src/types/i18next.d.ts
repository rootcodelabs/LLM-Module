import 'i18next';

// t() returns a string, never null. Must match `returnNull: false` in GUI/i18n.ts.
declare module 'i18next' {
  interface CustomTypeOptions {
    returnNull: false;
  }
}
