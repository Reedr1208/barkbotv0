import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Animated,
  KeyboardAvoidingView,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  useWindowDimensions,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Image } from 'expo-image';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { SlidersHorizontal, Shuffle, Send, ChevronDown, Check } from 'lucide-react-native';
import { api, ApiError, ChatMessage, Dog, LocationOption } from '../../src/api';
import { useAuth } from '../../src/auth';
import { colors, font, radius, spacing, shadow } from '../../src/theme';
import { dogAge, dogSex, resolveDogImage } from '../../src/utils';
import { EmptyState } from '../../src/components/common';
import { DogHeroView, DogDetailsView } from '../../src/components/DogProfileView';
import { OverlayModal } from '../../src/components/OverlayModal';
import { AboutModal } from '../../src/components/AboutModal';
import { PreferencesView } from '../../src/components/PreferencesView';
import { MyDogsView } from '../../src/components/MyDogsView';

export default function Discover() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const { email, isLoggedIn, preferences, favorites, savePreferences } = useAuth();

  const isDesktop = width >= 800;
  const savedCount = Object.keys(favorites).length;

  // Modals Visibility
  const [aboutVisible, setAboutVisible] = useState(false);
  const [prefVisible, setPrefVisible] = useState(false);
  const [savedVisible, setSavedVisible] = useState(false);
  const [locVisible, setLocVisible] = useState(false);

  // Locations list for header dropdown
  const [locations, setLocations] = useState<LocationOption[]>([]);
  
  // Active Dog Profile States
  const [dog, setDog] = useState<Dog | null>(null);
  const [loading, setLoading] = useState(true);
  const [empty, setEmpty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const viewedRef = useRef<string[]>([]);
  const reqId = useRef(0);

  // Chat Panel States
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(true);

  // Layout Scrolling Refs & Offsets
  const scrollRef = useRef<ScrollView>(null);
  const rightScrollRef = useRef<ScrollView>(null);
  const [chatY, setChatY] = useState(0);
  const [showStickyBar, setShowStickyBar] = useState(false);

  const prefsKey = `${email}|${preferences.gender}|${preferences.age_group}|${preferences.size}|${preferences.location}`;

  // Fetch Locations list
  useEffect(() => {
    api
      .locations()
      .then(({ locations }) => setLocations(locations || []))
      .catch(() => {});
  }, []);

  // Fetch Random Dog
  const fetchDog = useCallback(async () => {
    const myReq = ++reqId.current;
    setLoading(true);
    setError(null);
    setEmpty(false);
    try {
      const params = isLoggedIn
        ? { email: email ?? undefined, viewed: viewedRef.current }
        : {
            gender: preferences.gender,
            age_group: preferences.age_group,
            size: preferences.size,
            location: preferences.location,
            viewed: viewedRef.current,
          };
      const next = await api.randomDog(params);
      if (myReq !== reqId.current) return; // superseded
      setDog(next);
      if (next?.animal_id && !viewedRef.current.includes(next.animal_id)) {
        viewedRef.current = [...viewedRef.current, next.animal_id].slice(-40);
      }
    } catch (e) {
      if (myReq !== reqId.current) return;
      if (e instanceof ApiError && e.status === 404) {
        setEmpty(true);
        setDog(null);
      } else {
        setError(e instanceof Error ? e.message : 'Something went wrong.');
      }
    } finally {
      if (myReq === reqId.current) setLoading(false);
    }
  }, [email, isLoggedIn, preferences.gender, preferences.age_group, preferences.size, preferences.location]);

  // Load specific dog from saved list
  const loadDogById = async (animalId: string) => {
    setLoading(true);
    setError(null);
    setEmpty(false);
    try {
      const next = await api.randomDog({ animal_id: animalId });
      setDog(next);
    } catch (e) {
      setError('Could not load dog profile. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Refetch whenever identity/preferences change
  useEffect(() => {
    viewedRef.current = [];
    fetchDog();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefsKey]);

  // Chat message history loader
  useEffect(() => {
    if (!dog) return;
    let cancelled = false;
    setMessages([]);
    setLoadingHistory(true);
    
    (async () => {
      if (!email) {
        setLoadingHistory(false);
        return;
      }
      try {
        const { messages: prior } = await api.chatMessages(email, dog.animal_id);
        if (!cancelled && prior?.length) {
          setMessages(prior);
        }
      } catch {
        /* start fresh */
      } finally {
        if (!cancelled) setLoadingHistory(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [dog?.animal_id, email]);

  const scrollToChatBottom = () => {
    requestAnimationFrame(() => {
      if (isDesktop) {
        rightScrollRef.current?.scrollToEnd({ animated: true });
      } else {
        scrollRef.current?.scrollToEnd({ animated: true });
      }
    });
  };

  // Send message function
  const send = async (text: string) => {
    const message = text.trim();
    if (!message || sending || !dog) return;
    setInput('');

    const history = messages.slice(-12);
    const userMsg: ChatMessage = { role: 'user', content: message };
    setMessages((m) => [...m, userMsg]);
    setSending(true);

    scrollToChatBottom();

    try {
      const { reply } = await api.chat({
        animal_id: dog.animal_id,
        message,
        conversation_history: history,
        email: email ?? undefined,
        dog_name: dog.name,
        dog_image_url: resolveDogImage(dog) ?? undefined,
      });
      setMessages((m) => [...m, { role: 'assistant', content: reply }]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: '_Sorry, I had trouble responding to that. Please try again._' },
      ]);
    } finally {
      setSending(false);
      scrollToChatBottom();
    }
  };

  // Smooth scroll down to chat panel
  const scrollToChat = () => {
    if (isDesktop) {
      rightScrollRef.current?.scrollTo({ y: chatY, animated: true });
    } else {
      scrollRef.current?.scrollTo({ y: chatY, animated: true });
    }
  };

  const handleSelectDog = (animalId: string) => {
    setSavedVisible(false);
    loadDogById(animalId);
  };

  const selectLocation = async (locName: string) => {
    setLocVisible(false);
    await savePreferences({ location: locName });
  };

  const showAllDogs = async () => {
    await savePreferences({ gender: 'any', age_group: 'any', size: 'any', location: 'any' });
  };

  // ---------------------------------------------------------------------------
  // Sub-views
  // ---------------------------------------------------------------------------

  const header = (
    <View style={styles.header}>
      <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: spacing.lg }}>
        <Pressable onPress={() => setAboutVisible(true)}>
          <Text style={styles.brand}>Chattyhound</Text>
        </Pressable>
        
        {/* Navigation tabs */}
        <View style={styles.headerTabs}>
          <Pressable style={styles.headerTab} onPress={() => setAboutVisible(true)}>
            <Text style={styles.headerTabText}>About</Text>
          </Pressable>
          <Pressable style={styles.headerTabIcon} onPress={() => setPrefVisible(true)}>
            <SlidersHorizontal size={14} color={colors.textMuted} />
          </Pressable>
          <Pressable style={styles.headerTab} onPress={() => setSavedVisible(true)}>
            <View style={{ flexDirection: 'row', alignItems: 'center' }}>
              <Text style={styles.headerTabText}>My Dogs</Text>
              {savedCount > 0 && <View style={styles.savedBadgeDot} />}
            </View>
          </Pressable>
        </View>
      </View>

      <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}>
        {/* Location Dropdown */}
        <Pressable style={styles.locationSelector} onPress={() => setLocVisible(true)}>
          <Text style={styles.locationText} numberOfLines={1}>
            {preferences.location === 'any' ? 'All Locations 🌎' : preferences.location}
          </Text>
          <ChevronDown size={14} color={colors.textFaint} />
        </Pressable>

        {/* Shuffle next button */}
        <Pressable
          accessibilityLabel="Next dog"
          onPress={fetchDog}
          disabled={loading}
          style={[styles.nextBtn, loading && { opacity: 0.7 }]}
        >
          <Shuffle size={14} color={colors.accentText} />
          {isDesktop && <Text style={styles.nextBtnText}>Next Dog 🐶</Text>}
        </Pressable>
      </View>
    </View>
  );

  const desktopFooterInput = dog && (
    <View style={styles.footerInputBarDesktop}>
      <View style={styles.inputWrapper}>
        <TextInput
          style={styles.textInput}
          value={input}
          onChangeText={setInput}
          placeholder={`Ask ${dog.name} anything!`}
          placeholderTextColor={colors.textFaint}
          multiline
          onSubmitEditing={() => send(input)}
          returnKeyType="send"
          blurOnSubmit={false}
          editable={!loading && !sending}
        />
        <Pressable
          accessibilityLabel="Send message"
          onPress={() => send(input)}
          disabled={!input.trim() || sending}
          style={[styles.sendBtn, (!input.trim() || sending) && styles.sendBtnDisabled]}
        >
          <Send size={16} color={colors.accentText} />
        </Pressable>
      </View>
    </View>
  );

  const mobileFooterInput = dog && (
    <View style={[styles.footerInputBarMobile, { paddingBottom: insets.bottom + 8 }]}>
      <View style={styles.inputWrapper}>
        <TextInput
          style={styles.textInput}
          value={input}
          onChangeText={setInput}
          placeholder={`Ask ${dog.name} anything!`}
          placeholderTextColor={colors.textFaint}
          multiline
          onSubmitEditing={() => send(input)}
          returnKeyType="send"
          blurOnSubmit={false}
          editable={!loading && !sending}
        />
        <Pressable
          accessibilityLabel="Send message"
          onPress={() => send(input)}
          disabled={!input.trim() || sending}
          style={[styles.sendBtn, (!input.trim() || sending) && styles.sendBtnDisabled]}
        >
          <Send size={16} color={colors.accentText} />
        </Pressable>
      </View>
    </View>
  );

  const stickyDogBar = dog && showStickyBar && !isDesktop && (
    <View style={[styles.stickyDogBar, { top: 58 }]}>
      <Image source={{ uri: resolveDogImage(dog) }} style={styles.stickyAvatar} />
      <View style={{ flex: 1 }}>
        <Text style={styles.stickyName}>{dog.name}</Text>
        <Text style={styles.stickyMeta} numberOfLines={1}>
          {[dogSex(dog), dogAge(dog)].filter(Boolean).join(' · ')}
        </Text>
      </View>
      <View style={styles.stickyActions}>
        <Pressable style={styles.stickyActionBtn} onPress={scrollToChat}>
          <Text style={styles.stickyActionText}>Chat 💬</Text>
        </Pressable>
        {dog.shelter_url ? (
          <Pressable style={styles.stickyActionBtn} onPress={() => Linking.openURL(dog.shelter_url || '')}>
            <Text style={styles.stickyActionText}>Shelter 🛡️</Text>
          </Pressable>
        ) : null}
        <Pressable
          style={[styles.stickyActionBtn, styles.stickyNextBtn]}
          onPress={fetchDog}
          disabled={loading}
        >
          <Text style={styles.stickyNextText}>Next</Text>
        </Pressable>
      </View>
    </View>
  );

  return (
    <View style={isDesktop ? styles.rootDesktop : styles.rootMobile}>
      <View style={isDesktop ? styles.appContainerDesktop : styles.appContainerMobile}>
        {header}

        <KeyboardAvoidingView
          style={{ flex: 1 }}
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 0}
        >
          {loading ? (
            <View style={styles.centerWrap}>
              <ActivityIndicator color={colors.accent} size="large" />
              <Text style={styles.loadingMsg}>Sniffing out your match...</Text>
            </View>
          ) : empty ? (
            <EmptyState
              title="No perfect matches yet"
              description="Every rescue pup has unique charm! We don't have a dog matching your exact preferences right now, but we update constantly. Try adjusting your preferences or exploring all dogs."
              primaryLabel="Adjust Preferences 🛠️"
              onPrimary={() => setPrefVisible(true)}
              secondaryLabel="Show me all dogs"
              onSecondary={showAllDogs}
            />
          ) : error ? (
            <EmptyState
              icon="😕"
              title="Couldn't load a dog"
              description={error}
              primaryLabel="Try again"
              onPrimary={fetchDog}
            />
          ) : dog ? (
            isDesktop ? (
              // ── Desktop Dual-Pane Grid Layout ──
              <View style={styles.splitPane}>
                {/* Left image column */}
                <View style={styles.leftColumn}>
                  <DogHeroView dog={dog} isDesktop />
                </View>

                {/* Right details scroll column */}
                <View style={styles.rightColumn}>
                  <ScrollView
                    ref={rightScrollRef}
                    contentContainerStyle={{ paddingBottom: 110 }}
                    showsVerticalScrollIndicator={true}
                  >
                    <DogDetailsView
                      dog={dog}
                      email={email}
                      onChat={scrollToChat}
                      onSendMessage={send}
                      messages={messages}
                      sending={sending}
                      loadingHistory={loadingHistory}
                      onChatLayout={(e) => setChatY(e.nativeEvent.layout.y)}
                    />
                    
                    {/* Big footer button */}
                    <View style={styles.shuffleFooter}>
                      <Pressable style={styles.shuffleBig} onPress={fetchDog} disabled={loading}>
                        {loading ? (
                          <ActivityIndicator color={colors.textMain} />
                        ) : (
                          <>
                            <Shuffle size={18} color={colors.textMain} />
                            <Text style={styles.shuffleBigText}>Show me another dog</Text>
                          </>
                        )}
                      </Pressable>
                    </View>
                  </ScrollView>

                  {/* Sticky input */}
                  {desktopFooterInput}
                </View>
              </View>
            ) : (
              // ── Mobile Linear Scroll Layout ──
              <View style={{ flex: 1 }}>
                <ScrollView
                  ref={scrollRef}
                  contentContainerStyle={{ paddingBottom: 120 }}
                  onScroll={(e) => {
                    const offset = e.nativeEvent.contentOffset.y;
                    setShowStickyBar(offset > 320);
                  }}
                  scrollEventThrottle={16}
                  showsVerticalScrollIndicator={false}
                >
                  <DogHeroView dog={dog} />
                  <DogDetailsView
                    dog={dog}
                    email={email}
                    onChat={scrollToChat}
                    onSendMessage={send}
                    messages={messages}
                    sending={sending}
                    loadingHistory={loadingHistory}
                    onChatLayout={(e) => setChatY(e.nativeEvent.layout.y + 320)}
                  />

                  {/* Big footer button */}
                  <View style={styles.shuffleFooter}>
                    <Pressable style={styles.shuffleBig} onPress={fetchDog} disabled={loading}>
                      {loading ? (
                        <ActivityIndicator color={colors.textMain} />
                      ) : (
                        <>
                          <Shuffle size={18} color={colors.textMain} />
                          <Text style={styles.shuffleBigText}>Show me another dog</Text>
                        </>
                      )}
                    </Pressable>
                  </View>
                </ScrollView>

                {/* Sticky input */}
                {mobileFooterInput}

                {/* Sticky dog bar overlay */}
                {stickyDogBar}
              </View>
            )
          ) : null}
        </KeyboardAvoidingView>
      </View>

      {/* ────────────────────────────────────────── */}
      {/* Navigation Modals Overlays */}
      {/* ────────────────────────────────────────── */}

      {/* 1. About Modal */}
      <OverlayModal visible={aboutVisible} onClose={() => setAboutVisible(false)}>
        <AboutModal onClose={() => setAboutVisible(false)} />
      </OverlayModal>

      {/* 2. Preferences (Fit) Modal */}
      <OverlayModal visible={prefVisible} onClose={() => setPrefVisible(false)}>
        <PreferencesView onClose={() => setPrefVisible(false)} />
      </OverlayModal>

      {/* 3. Saved Dogs Modal */}
      <OverlayModal visible={savedVisible} onClose={() => setSavedVisible(false)}>
        <MyDogsView
          onSelectDog={handleSelectDog}
          onClose={() => setSavedVisible(false)}
        />
      </OverlayModal>

      {/* 4. Location Custom Selector Modal */}
      <OverlayModal visible={locVisible} onClose={() => setLocVisible(false)}>
        <View style={{ gap: spacing.md }}>
          <View style={{ paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.borderSoft }}>
            <Text style={{ fontFamily: font.black, fontSize: 18, color: colors.textMain }}>Filter by Location</Text>
            <Text style={{ fontFamily: font.medium, fontSize: 12.5, color: colors.textMuted, marginTop: 4 }}>
              Prioritize shelter listings located in a specific area.
            </Text>
          </View>
          <ScrollView style={{ maxHeight: 320 }} showsVerticalScrollIndicator={false}>
            <View style={{ gap: 8 }}>
              <Pressable
                style={[styles.locItemRow, preferences.location === 'any' && styles.locItemRowActive]}
                onPress={() => selectLocation('any')}
              >
                <Text style={styles.locItemText}>All Locations 🌎</Text>
                {preferences.location === 'any' && <Check size={16} color={colors.accent} />}
              </Pressable>
              {locations.map((loc) => {
                const isActive = preferences.location === loc.display_name;
                return (
                  <Pressable
                    key={loc.display_name}
                    style={[styles.locItemRow, isActive && styles.locItemRowActive]}
                    onPress={() => selectLocation(loc.display_name)}
                  >
                    <Text style={styles.locItemText}>{loc.display_name}</Text>
                    {isActive && <Check size={16} color={colors.accent} />}
                  </Pressable>
                );
              })}
            </View>
          </ScrollView>
        </View>
      </OverlayModal>
    </View>
  );
}

const styles = StyleSheet.create({
  // Root and outer framing
  rootDesktop: {
    flex: 1,
    backgroundColor: '#020617', // Centered Cinematic Frame Background
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 32,
    paddingHorizontal: spacing.xxl,
  },
  rootMobile: {
    flex: 1,
    backgroundColor: colors.slate950,
  },
  appContainerDesktop: {
    width: '100%',
    maxWidth: 1280,
    height: '100%',
    maxHeight: 860,
    borderRadius: 32,
    borderWidth: 1.5,
    borderColor: colors.borderSoft,
    backgroundColor: colors.slate950,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 35 },
    shadowOpacity: 0.7,
    shadowRadius: 80,
    elevation: 12,
  },
  appContainerMobile: {
    flex: 1,
    backgroundColor: colors.slate950,
  },

  // Top header layout
  header: {
    height: 58,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    backgroundColor: 'rgba(2,6,23,0.92)',
    borderBottomWidth: 1.5,
    borderBottomColor: colors.borderSoft,
    zIndex: 10,
  },
  brand: {
    fontFamily: font.black,
    fontSize: 18,
    color: colors.textMain,
    letterSpacing: -0.3,
  },
  headerTabs: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginLeft: spacing.lg,
  },
  headerTab: {
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: radius.sm,
  },
  headerTabIcon: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.surfaceFaint,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    alignItems: 'center',
    justifyContent: 'center',
    marginHorizontal: 2,
  },
  headerTabText: {
    fontFamily: font.bold,
    fontSize: 13,
    color: colors.textMuted,
  },
  savedBadgeDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.accent,
    marginLeft: 4,
    marginTop: -4,
  },

  // Header Dropdown and buttons
  locationSelector: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    borderRadius: radius.pill,
    paddingHorizontal: 12,
    paddingVertical: 5,
    maxWidth: 160,
  },
  locationText: {
    fontFamily: font.bold,
    fontSize: 11.5,
    color: colors.textMain,
  },
  nextBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: colors.accent,
    paddingHorizontal: 14,
    height: 32,
    borderRadius: radius.pill,
    ...shadow.accent,
  },
  nextBtnText: {
    fontFamily: font.extrabold,
    fontSize: 12,
    color: colors.accentText,
  },

  // Split-pane layout
  splitPane: {
    flex: 1,
    flexDirection: 'row',
    overflow: 'hidden',
  },
  leftColumn: {
    width: '52%',
    height: '100%',
  },
  rightColumn: {
    width: '48%',
    height: '100%',
    position: 'relative',
    backgroundColor: colors.slate950,
  },

  // State loading helpers
  centerWrap: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
  },
  loadingMsg: {
    fontFamily: font.semibold,
    fontSize: 14.5,
    color: colors.textFaint,
  },

  // Shuffle footer big button
  shuffleFooter: {
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.xs,
    paddingBottom: spacing.xl,
  },
  shuffleBig: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    height: 50,
    borderRadius: radius.pill,
    borderWidth: 1.5,
    borderColor: colors.borderSoft,
    backgroundColor: colors.surfaceFaint,
  },
  shuffleBigText: {
    fontFamily: font.extrabold,
    fontSize: 14,
    color: colors.textMain,
  },

  // Sticky bottom input bar (Web / Desktop overlay)
  footerInputBarDesktop: {
    position: 'absolute',
    bottom: 24,
    left: 24,
    right: 24,
    zIndex: 100,
  },
  // Sticky bottom input bar (Mobile screen layout)
  footerInputBarMobile: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: 'rgba(2,6,23,0.92)',
    borderTopWidth: 1,
    borderTopColor: colors.borderSoft,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    zIndex: 100,
  },
  inputWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderRadius: 9999,
    backgroundColor: 'rgba(2, 6, 23, 0.95)',
    borderWidth: 1.5,
    borderColor: colors.borderSoft,
    padding: 6,
    paddingHorizontal: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.5,
    shadowRadius: 16,
    elevation: 8,
  },
  textInput: {
    flex: 1,
    minHeight: 38,
    maxHeight: 80,
    color: colors.textMain,
    fontFamily: font.medium,
    fontSize: 14.5,
    paddingHorizontal: spacing.xs,
    paddingTop: 8,
    paddingBottom: 8,
  },
  sendBtn: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: colors.accent,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendBtnDisabled: {
    opacity: 0.4,
  },

  // Slide-down sticky dog bar on scroll (mobile only)
  stickyDogBar: {
    position: 'absolute',
    left: 0,
    right: 0,
    height: 52,
    backgroundColor: 'rgba(2,6,23,0.96)',
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSoft,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    gap: spacing.sm,
    zIndex: 90,
  },
  stickyAvatar: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: colors.slate800,
  },
  stickyName: {
    fontFamily: font.black,
    fontSize: 14,
    color: colors.textMain,
  },
  stickyMeta: {
    fontFamily: font.semibold,
    fontSize: 10.5,
    color: colors.textFaint,
    marginTop: 1,
  },
  stickyActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  stickyActionBtn: {
    paddingVertical: 5,
    paddingHorizontal: 8,
    borderRadius: radius.sm,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.borderSoft,
  },
  stickyActionText: {
    fontFamily: font.bold,
    fontSize: 11,
    color: colors.textMain,
  },
  stickyNextBtn: {
    backgroundColor: colors.accent,
    borderColor: colors.accent,
  },
  stickyNextText: {
    fontFamily: font.extrabold,
    fontSize: 11,
    color: colors.accentText,
  },

  // Custom Selector modal styling
  locItemRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderRadius: radius.sm,
    backgroundColor: colors.surfaceFaint,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  locItemRowActive: {
    backgroundColor: 'rgba(245, 158, 11, 0.05)',
    borderColor: colors.amberBorder,
  },
  locItemText: {
    fontFamily: font.bold,
    fontSize: 14,
    color: colors.textMain,
  },
});
