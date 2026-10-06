"use client";
import { useSettings } from '@/components/settings/SettingsContext';
import { inputClass, sectionTitleClass } from '@/components/settings/settingsStyles';
import React from 'react';

export const selectTriggerClass = 'h-9 text-xs font-semibold';

export const FieldLabel = ({ label, children }: { label: string; children: React.ReactNode }) => {
  const { theme } = useSettings();
  return <label className="block space-y-1.5"><span className={sectionTitleClass(theme)}>{label}</span>{children}</label>;
};
export const SelectField = FieldLabel;
export const Field = ({ label, value, set, secret = false, placeholder = '' }: { label: string; value: string; set: (value: string) => void; secret?: boolean; placeholder?: string }) => {
  const { theme } = useSettings();
  return <FieldLabel label={label}><input type={secret ? 'password' : 'text'} className={inputClass(theme)} value={value} placeholder={placeholder} onChange={event => set(event.target.value)} /></FieldLabel>;
};
export const NumberField = ({ label, value, set }: { label: string; value: number; set: (value: number) => void }) => {
  const { theme } = useSettings();
  return <FieldLabel label={label}><input type="number" min="1" className={inputClass(theme)} value={value} onChange={event => set(Number(event.target.value))} /></FieldLabel>;
};
