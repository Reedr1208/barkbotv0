import React from 'react';
import { Modal, Platform, Pressable, StyleSheet, View } from 'react-native';
import { X } from 'lucide-react-native';
import { colors, radius, spacing } from '../theme';

interface OverlayModalProps {
  visible: boolean;
  onClose: () => void;
  children: React.ReactNode;
}

export function OverlayModal({ visible, onClose, children }: OverlayModalProps) {
  if (!visible) return null;

  // React Native's Modal can be buggy or not support flex centering cleanly on web,
  // so we use a custom absolute-positioned view on Web, and standard Modal on Native.
  if (Platform.OS === 'web') {
    return (
      <View style={styles.webContainer}>
        <Pressable style={styles.backdrop} onPress={onClose} />
        <View style={styles.card}>
          <Pressable onPress={onClose} style={styles.closeBtn} hitSlop={8}>
            <X size={18} color={colors.textMuted} />
          </Pressable>
          <View style={styles.content}>{children}</View>
        </View>
      </View>
    );
  }

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={onClose}
    >
      <View style={styles.modalContainer}>
        <Pressable style={styles.backdrop} onPress={onClose} />
        <View style={styles.card}>
          <Pressable onPress={onClose} style={styles.closeBtn} hitSlop={8}>
            <X size={18} color={colors.textMuted} />
          </Pressable>
          <View style={styles.content}>{children}</View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  webContainer: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    zIndex: 1000,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.lg,
  },
  modalContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.lg,
  },
  backdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(2, 6, 23, 0.85)',
  },
  card: {
    width: '100%',
    maxWidth: 480,
    maxHeight: '85%',
    backgroundColor: colors.slate900,
    borderRadius: radius.xl,
    borderWidth: 1.5,
    borderColor: colors.borderSoft,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 20 },
    shadowOpacity: 0.6,
    shadowRadius: 30,
    elevation: 10,
  },
  closeBtn: {
    position: 'absolute',
    top: 16,
    right: 16,
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.slate800,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 10,
    borderWidth: 1,
    borderColor: colors.borderSoft,
  },
  content: {
    padding: spacing.xl,
    paddingTop: spacing.xxl,
  },
});
