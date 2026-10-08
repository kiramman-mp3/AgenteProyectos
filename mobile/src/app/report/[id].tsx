import { useLocalSearchParams } from 'expo-router';
import { useCallback } from 'react';
import { Share } from 'react-native';

import { Markdown } from '@/components/Markdown';
import { Button, Card, ErrorBox, Loading, Row, Screen, useLoader } from '@/components/ui';
import { api } from '@/lib/api';

export default function ReportDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const loader = useCallback(() => api.report(Number(id)), [id]);
  const { data, error } = useLoader(loader);

  if (!data && !error) return <Loading />;
  if (!data) return <Screen><ErrorBox message={error!} /></Screen>;

  return (
    <Screen>
      <Row>
        <Button label="Compartir" variant="secondary" onPress={() => Share.share({ message: data.content_md })} />
      </Row>
      <Card>
        <Markdown>
          {data.content_md}
        </Markdown>
      </Card>
    </Screen>
  );
}
